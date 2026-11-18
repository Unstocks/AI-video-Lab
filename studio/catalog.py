"""Whole-system catalog & discovery serializers for AI Video Lab Studio.

Reads live pipeline manifests (``pipeline_defs/*.yaml``), style playbooks
(``styles/*.yaml`` + ``styles/custom/*.yaml``), media profiles, the 169-tool
``ToolRegistry``, and ``config.yaml``.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import yaml

from lib.media_profiles import ALL_PROFILES
from lib.paths import REPO_ROOT
from lib.pipeline_loader import list_pipelines, load_pipeline_readonly
from styles.playbook_loader import list_playbooks, load_playbook
from tools.tool_registry import ToolRegistry

_TOOLS_CACHE_LOCK = threading.Lock()
_TOOLS_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_TOOLS_TTL_SECONDS = 60.0


def get_pipelines_catalog() -> list[dict[str, Any]]:
    """Serialize all pipeline manifests with stage rails, gates, and playbooks."""
    items: list[dict[str, Any]] = []
    for name in sorted(list_pipelines()):
        try:
            m = load_pipeline_readonly(name)
        except Exception:
            continue
        orch = m.get("orchestration") or {}
        ref = m.get("reference_input") or {}
        compat = m.get("compatible_playbooks") or {}
        stages = [
            {
                "name": str(s.get("name") or ""),
                "gated": bool(s.get("human_approval_default", False)),
                "checkpoint_required": bool(s.get("checkpoint_required", False)),
                "produces": [str(x) for x in (s.get("produces") or []) if isinstance(x, str)],
            }
            for s in (m.get("stages") or [])
            if isinstance(s, dict) and s.get("name")
        ]
        items.append({
            "name": str(m.get("name") or name),
            "version": str(m.get("version") or "1.0"),
            "description": " ".join(str(m.get("description") or "").split()),
            "category": str(m.get("category") or "general"),
            "stability": str(m.get("stability") or "beta"),
            "default_checkpoint_policy": str(m.get("default_checkpoint_policy") or "guided"),
            "budget_default_usd": float(orch.get("budget_default_usd") or 2.0),
            "reference_input_supported": bool(ref.get("supported", False)),
            "compatible_playbooks": {
                "recommended": list(compat.get("recommended") or []),
                "also_works": list(compat.get("also_works") or []),
                "custom_allowed": bool(compat.get("custom_allowed", True)),
            },
            "stages": stages,
            "stage_count": len(stages),
            "gated_stages": [s["name"] for s in stages if s["gated"]],
        })
    # Sort production first, clip-factory & flagship pipelines at top
    priority = {
        "clip-factory": 0,
        "animated-explainer": 1,
        "cinematic": 2,
        "podcast-repurpose": 3,
        "animation": 4,
        "character-animation": 5,
        "talking-head": 6,
        "screen-demo": 7,
        "documentary-montage": 8,
        "hybrid": 9,
        "avatar-spokesperson": 10,
        "localization-dub": 11,
        "framework-smoke": 99,
    }
    items.sort(key=lambda x: (priority.get(x["name"], 50), x["name"]))
    return items


def get_playbooks_catalog() -> list[dict[str, Any]]:
    """Serialize all visual style playbooks with palette swatches and typography."""
    items: list[dict[str, Any]] = []
    for name in list_playbooks():
        try:
            pb = load_playbook(name)
        except Exception:
            continue
        ident = pb.get("identity") or {}
        vl = pb.get("visual_language") or {}
        pal = vl.get("color_palette") or {}
        typo = pb.get("typography") or {}
        audio = pb.get("audio") or {}
        motion = pb.get("motion") or {}
        items.append({
            "slug": name,
            "name": str(ident.get("name") or name),
            "category": str(ident.get("category") or "general"),
            "mood": str(ident.get("mood") or ""),
            "pace": str(ident.get("pace") or "moderate"),
            "best_for": str(ident.get("best_for") or ""),
            "palette": {
                "primary": list(pal.get("primary") or []),
                "accent": list(pal.get("accent") or []),
                "background": str(pal.get("background") or "#0F1117"),
                "text": str(pal.get("text") or "#F8FAFC"),
                "muted": str(pal.get("muted") or "#94A3B8"),
            },
            "typography": {
                "heading_font": str((typo.get("headings") or {}).get("font") or "Inter"),
                "body_font": str((typo.get("body") or {}).get("font") or "Inter"),
                "code_font": str((typo.get("code") or {}).get("font") or "JetBrains Mono"),
            },
            "motion_style": str(motion.get("animation_style") or ""),
            "music_mood": str(audio.get("music_mood") or ""),
        })
    return items


def get_media_profiles_catalog() -> list[dict[str, Any]]:
    """Serialize all platform media profiles."""
    out: list[dict[str, Any]] = []
    for p in ALL_PROFILES.values():
        out.append({
            "name": p.name,
            "width": p.width,
            "height": p.height,
            "aspect_ratio": p.aspect_ratio.value,
            "fps": p.fps,
            "codec": p.codec,
            "audio_codec": p.audio_codec,
            "crf": p.crf,
            "pixel_format": p.pixel_format,
            "max_file_size_mb": p.max_file_size_mb,
            "max_duration_seconds": p.max_duration_seconds,
            "caption_format": p.caption_format,
            "notes": p.notes,
        })
    return out


def get_tools_catalog(*, force_refresh: bool = False) -> dict[str, Any]:
    """Discover and cache the full 169-tool registry snapshot in a single parallel pass."""
    from concurrent.futures import ThreadPoolExecutor

    now = time.monotonic()
    with _TOOLS_CACHE_LOCK:
        cached = _TOOLS_CACHE.get("data")
        if not force_refresh and cached is not None and (now - float(_TOOLS_CACHE.get("ts") or 0.0)) < _TOOLS_TTL_SECONDS:
            return cached

    reg = ToolRegistry()
    reg.ensure_discovered()
    all_tools = [reg.get(name) for name in sorted(reg.list_all())]
    valid_tools = [t for t in all_tools if t is not None]

    def _probe_one(tool: Any) -> tuple[Any, dict[str, Any]]:
        try:
            return tool, tool.get_info()
        except Exception:
            return tool, {"status": "unavailable"}

    with ThreadPoolExecutor(max_workers=12) as pool:
        probed = list(pool.map(_probe_one, valid_tools))

    tools_list: list[dict[str, Any]] = []
    counts = {"available": 0, "degraded": 0, "unavailable": 0}
    tiers: dict[str, dict[str, int]] = {}
    cap_buckets: dict[str, dict[str, Any]] = {}
    setup_offers: list[dict[str, Any]] = []
    comp_runtimes: dict[str, bool] = {}
    runtime_warnings: list[str] = []

    for tool, info in probed:
        status = str(info.get("status") or "unavailable")
        counts[status] = counts.get(status, 0) + 1

        tier_val = str(tool.tier.value)
        tier_bucket = tiers.setdefault(tier_val, {"available": 0, "unavailable": 0, "degraded": 0})
        tier_bucket[status] = tier_bucket.get(status, 0) + 1

        if tool.name == "video_compose":
            engines = info.get("render_engines") or {}
            comp_runtimes = {k: bool(v) for k, v in engines.items()}
        elif tool.name == "hyperframes_compose":
            rc = info.get("hyperframes_runtime") or {}
            for reason in rc.get("reasons") or []:
                runtime_warnings.append(f"hyperframes: {reason}")
        elif tool.name == "diagram_gen":
            op_st = info.get("operation_statuses") or {}
            if op_st.get("mermaid") != "available":
                runtime_warnings.append(
                    "diagram_gen: Mermaid CLI (mmdc) is unavailable; Pillow fallback active"
                )

        if tool.provider != "selector":
            cap = str(tool.capability)
            cb = cap_buckets.setdefault(
                cap,
                {"configured": 0, "total": 0, "avail_p": set(), "unavail_p": set()},
            )
            cb["total"] += 1
            if status == "available":
                cb["configured"] += 1
                if tool.provider:
                    cb["avail_p"].add(str(tool.provider))
            else:
                if tool.provider:
                    cb["unavail_p"].add(str(tool.provider))
                inst = str(tool.install_instructions or "").strip()
                if inst and len(inst) <= 220 and ("API_KEY" in inst or "TOKEN" in inst or "pip install" in inst):
                    setup_offers.append({
                        "capability": cap,
                        "tool": tool.name,
                        "install_instructions": inst,
                    })

        tools_list.append({
            "name": tool.name,
            "capability": str(tool.capability),
            "provider": str(tool.provider),
            "tier": tier_val,
            "runtime": str(tool.runtime.value),
            "stability": str(tool.stability.value),
            "status": status,
            "best_for": list(tool.best_for or []),
            "dependencies": list(info.get("dependencies") or getattr(tool, "dependencies", []) or []),
            "install_instructions": str(tool.install_instructions or ""),
        })

    capabilities = [
        {
            "capability": cap,
            "configured": b["configured"],
            "total": b["total"],
            "available_providers": sorted(b["avail_p"]),
            "unavailable_providers": sorted(b["unavail_p"] - b["avail_p"]),
        }
        for cap, b in sorted(cap_buckets.items())
    ]

    data = {
        "total": len(tools_list),
        "counts": counts,
        "composition_runtimes": comp_runtimes,
        "runtime_warnings": runtime_warnings,
        "capabilities": capabilities,
        "setup_offers": setup_offers,
        "tiers": tiers,
        "tools": tools_list,
    }
    with _TOOLS_CACHE_LOCK:
        _TOOLS_CACHE["ts"] = time.monotonic()
        _TOOLS_CACHE["data"] = data
    return data


def get_studio_config() -> dict[str, Any]:
    """Read OpenMontage global config.yaml safely."""
    cfg_path = REPO_ROOT / "config.yaml"
    if not cfg_path.is_file():
        return {}
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
