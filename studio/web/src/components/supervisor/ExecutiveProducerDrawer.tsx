import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';
import { useSystemStore } from '@/stores/useStudioStore';
import { ExecutiveProducerDock } from '@/components/supervisor/ExecutiveProducerDock';

export function ExecutiveProducerDrawer() {
  const { dockOpen, setDockOpen } = useSystemStore();

  useEffect(() => {
    if (!dockOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDockOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [dockOpen, setDockOpen]);

  return (
    <AnimatePresence>
      {dockOpen && (
        <div
          role="dialog"
          aria-label="Executive Producer Drawer"
          className="fixed inset-0 z-50 flex justify-end"
        >
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.16 }}
            onClick={() => setDockOpen(false)}
            className="absolute inset-0 bg-black/35 backdrop-blur-[2px]"
          />
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 360, damping: 34 }}
            className="relative z-10 flex h-full max-w-[92vw] shadow-[var(--shadow-float)]"
          >
            <button
              type="button"
              onClick={() => setDockOpen(false)}
              aria-label="Close Executive Producer Drawer"
              title="Close Producer (Esc)"
              className="absolute -left-10 top-3 flex h-8 w-8 items-center justify-center rounded-full border border-[var(--border-strong)] bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-md hover:bg-[var(--bg-panel)] cursor-pointer"
            >
              <X className="h-4 w-4" />
            </button>
            <ExecutiveProducerDock />
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
