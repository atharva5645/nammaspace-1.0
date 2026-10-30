import { Script } from 'playcanvas';
import { CameraRailControls } from './CameraRailControls';
import type { NavigationConfig, Vec3Tuple } from '../types/scene';

/**
 * CameraRailScript — PlayCanvas Script wrapper for CameraRailControls.
 * Loads the rail JSON, initialises the controller, and ticks it each frame.
 * Exposes a global `window.__cameraRail` handle so the UI layer can call
 * `goNext()` / `goPrev()` / `goTo(n)` directly.
 */
export class CameraRailScript extends Script {
    static scriptName = 'cameraRailScript';

    public navigation?: NavigationConfig;
    public initialPosition: Vec3Tuple = [0, 0.7, 0];

    private rail: CameraRailControls | null = null;

    initialize(): void {
        const railUrl = this.navigation?.railUrl ?? '/supermarket_rail.json';
        this.rail = new CameraRailControls(this.entity);

        this.rail.loadRail(railUrl).then(() => {
            this.rail!.initialize();
            // Expose globally so HUD buttons can navigate
            (window as any).__cameraRail = this.rail;
            console.log('[CameraRailScript] Ready. Use ← → arrows or scroll to navigate.');
        }).catch((err) => {
            console.error('[CameraRailScript] Failed to load rail:', err);
        });
    }

    update(dt: number): void {
        this.rail?.update(dt);
    }

    destroy(): void {
        this.rail?.destroy();
        (window as any).__cameraRail = null;
    }
}
