import { create } from 'zustand';
import { studioApi } from '@/lib/api';
import { toast } from '@/stores/useStudioStore';
import type { BrandKitRecord } from '@/types/studio';

interface BrandKitState {
  items: BrandKitRecord[];
  loading: boolean;
  loaded: boolean;
  loadBrandKit: (force?: boolean) => Promise<void>;
  saveItem: (
    category: BrandKitRecord['category'],
    name: string,
    payload: Record<string, unknown>,
  ) => Promise<BrandKitRecord | null>;
  removeItem: (itemId: string) => Promise<void>;
}

export const useBrandKitStore = create<BrandKitState>((set, get) => ({
  items: [],
  loading: false,
  loaded: false,

  loadBrandKit: async (force = false) => {
    if (get().loaded && !force) return;
    set({ loading: true });
    try {
      const res = await studioApi.listBrandKit();
      set({ items: res.items || [], loading: false, loaded: true });
    } catch {
      set({ loading: false, loaded: true });
    }
  },

  saveItem: async (category, name, payload) => {
    try {
      const created = await studioApi.addBrandKitItem({ category, name, payload });
      set((s) => ({ items: [created, ...s.items] }));
      toast.success('Saved to Brand Kit', name);
      return created;
    } catch (e) {
      toast.error('Save to Brand Kit failed', String(e));
      return null;
    }
  },

  removeItem: async (itemId) => {
    try {
      await studioApi.deleteBrandKitItem(itemId);
      set((s) => ({ items: s.items.filter((x) => x.item_id !== itemId) }));
      toast.info('Removed from Brand Kit');
    } catch (e) {
      toast.error('Could not delete item', String(e));
    }
  },
}));
