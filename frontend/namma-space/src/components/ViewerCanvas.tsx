import { Application, Entity } from '@playcanvas/react';
import { Camera, GSplat, Script } from '@playcanvas/react/components';
import { useSplat, useApp } from '@playcanvas/react/hooks';
import { DEVICETYPE_WEBGPU, DEVICETYPE_WEBGL2 } from 'playcanvas';
import React, { useEffect, useRef } from 'react';

import { FirstPersonControls } from '../controls/FirstPersonControls';
import type { SceneConfig } from '../types/scene';

const MIN_PIXEL_RATIO = 0.75;
const MAX_PIXEL_RATIO = 2;
const PIXEL_RATIO_STEP = 0.25;

/**
 * Adaptive render resolution. Starts sharp (up to 1.5x), then once per second checks
 * the frame rate: drops resolution when the GPU can't keep ~45 FPS, and raises it again
 * after a few seconds of steady ~58+ FPS. Fast GPUs get a crisp image, slow laptops stay smooth.
 */
function AdaptiveResolution() {
    const app = useApp();

    useEffect(() => {
        if (!app?.graphicsDevice) return;
        return startAdaptiveResolution(app);
    }, [app]);

    return null;
}

/** Runs the adaptive-resolution loop for an app; returns a cleanup function. */
function startAdaptiveResolution(app: NonNullable<ReturnType<typeof useApp>>): () => void {
    const device = app.graphicsDevice;

    const cap = () => Math.max(1, Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO));
    let ratio = Math.min(cap(), 1.5);
    let frames = 0;
    let last = performance.now();
    let goodSeconds = 0;
    let cooldown = 0;

    const apply = (next: number) => {
        next = Math.round(Math.max(MIN_PIXEL_RATIO, Math.min(cap(), next)) * 4) / 4;
        ratio = next;
        if (device.maxPixelRatio !== next) {
            device.maxPixelRatio = next;
            app.resizeCanvas();
        }
        debugWindow.__namma_pixel_ratio = next;
    };
    apply(ratio);

    const onFrame = () => {
        frames++;
    };
    app.on('framerender', onFrame);

    const timer = window.setInterval(() => {
        const now = performance.now();
        const fps = (frames * 1000) / Math.max(1, now - last);
        frames = 0;
        last = now;
        if (document.hidden) return;
        if (cooldown > 0) {
            cooldown--;
            return;
        }

        if (fps < 45 && ratio > MIN_PIXEL_RATIO) {
            apply(ratio - PIXEL_RATIO_STEP);
            goodSeconds = 0;
            cooldown = 2; // let the frame rate settle before judging again
        } else if (fps >= 58) {
            goodSeconds++;
            if (goodSeconds >= 3 && ratio < cap()) {
                apply(ratio + PIXEL_RATIO_STEP);
                goodSeconds = 0;
                cooldown = 2;
            }
        } else {
            goodSeconds = 0;
        }
    }, 1000);

    const onResize = () => apply(ratio);
    window.addEventListener('resize', onResize);
    return () => {
        window.clearInterval(timer);
        window.removeEventListener('resize', onResize);
        app.off('framerender', onFrame);
    };
}

type SplatBudgetConfiguratorProps = {
    splatBudget?: number;
    splatBudgetMode?: 'limit' | 'target';
};

/**
 * Configures the native PlayCanvas GSplat budget balancer on app.scene.gsplat
 * and exposes live octree/LOD runtime telemetry on window.__namma_lod.
 */
function SplatBudgetConfigurator({ splatBudget = 400000, splatBudgetMode = 'limit' }: SplatBudgetConfiguratorProps) {
    const app = useApp();

    useEffect(() => {
        if (!app?.scene?.gsplat) return;
        return startSplatTelemetry(app, splatBudget, splatBudgetMode);
    }, [app, splatBudget, splatBudgetMode]);

    return null;
}

// Minimal shapes of PlayCanvas internals read for the debug telemetry below.
// These are private engine fields, so every one is optional.
type OctreeInstanceInternals = {
    targetSplats?: number;
    activeSplats?: number;
    nodeLods?: ArrayLike<number>;
    octree?: { files?: { url: string }[]; fileRefCounts?: ArrayLike<number> };
};
type GsplatWorldInternals = {
    _octreeInstances?: Map<unknown, OctreeInstanceInternals>;
    currentVersion?: number;
    getState?: (version?: number) => { totalActiveSplats?: number } | undefined;
};
type GsplatDirectorInternals = {
    camerasMap?: Map<unknown, { layersMap?: Map<unknown, { gsplatManager?: { world?: GsplatWorldInternals } }> }>;
};
type TelemetryAsset = { type: string; loaded: boolean; name: string; file?: { url?: string } };

/** Debug values exposed on window for the inspector and manual checks in the console. */
type NammaDebugWindow = Window & {
    __namma_lod?: Record<string, unknown>;
    __namma_pixel_ratio?: number;
};
const debugWindow = window as NammaDebugWindow;

/** Applies the splat budget and samples LOD telemetry every 500 ms; returns a cleanup function. */
function startSplatTelemetry(
    app: NonNullable<ReturnType<typeof useApp>>,
    splatBudget: number,
    splatBudgetMode: 'limit' | 'target'
): () => void {
    const gsplat = app.scene.gsplat;
    gsplat.splatBudget = splatBudget;
    gsplat.splatBudgetMode = splatBudgetMode;

    let frameCount = 0;
    let lastTime = performance.now();
    let currentFps = 60;

    const intervalId = window.setInterval(() => {
        const now = performance.now();
        const elapsed = (now - lastTime) / 1000;
        if (elapsed > 0) {
            currentFps = Math.round(frameCount / elapsed);
            frameCount = 0;
            lastTime = now;
        }

        const renderer = (app as unknown as { renderer?: { gsplatDirector?: GsplatDirectorInternals } }).renderer;
        const director = renderer?.gsplatDirector;
        let octreeCount = 0;
        let activeSplats = 0;
        let targetSplats = 0;
        let lod0Count = 0;
        let lod1Count = 0;
        let totalNodes = 0;
        const fileRefCounts: Record<string, number> = {};

        director?.camerasMap?.forEach((camData) => {
            camData.layersMap?.forEach((layerData) => {
                const world = layerData.gsplatManager?.world;
                if (!world?._octreeInstances) return;
                octreeCount += world._octreeInstances.size;
                const state = world.getState?.(world.currentVersion);
                if (state?.totalActiveSplats) {
                    activeSplats = Math.max(activeSplats, state.totalActiveSplats);
                }
                world._octreeInstances.forEach((inst) => {
                    if (inst.targetSplats) targetSplats = inst.targetSplats;
                    if (inst.activeSplats) activeSplats = Math.max(activeSplats, inst.activeSplats);
                    if (inst.nodeLods) {
                        for (let i = 0; i < inst.nodeLods.length; i++) {
                            totalNodes++;
                            if (inst.nodeLods[i] === 0) lod0Count++;
                            else if (inst.nodeLods[i] === 1) lod1Count++;
                        }
                    }
                    const refCounts = inst.octree?.fileRefCounts;
                    if (inst.octree?.files && refCounts) {
                        inst.octree.files.forEach((f, idx) => {
                            fileRefCounts[f.url] = refCounts[idx];
                        });
                    }
                });
            });
        });

        const assets = app.assets as unknown as { filter: (fn: (a: TelemetryAsset) => boolean) => TelemetryAsset[] };
        const loadedGsplatAssets = assets
            .filter((a) => a.type === 'gsplat' && a.loaded)
            .map((a) => a.file?.url || a.name);

        debugWindow.__namma_lod = {
            isLodActive: octreeCount > 0,
            octreeCount,
            activeSplats,
            targetSplats,
            splatBudget: gsplat.splatBudget,
            splatBudgetMode: gsplat.splatBudgetMode,
            nodeLodDistribution: { lod0: lod0Count, lod1: lod1Count, total: totalNodes },
            fileRefCounts,
            loadedChunks: loadedGsplatAssets,
            fps: currentFps,
            debugMode: gsplat.debug,
            toggleDebugLod: (enable = true) => {
                gsplat.debug = enable ? 1 : 0;
            }
        };
    }, 500);

    const onFrameRender = () => {
        frameCount++;
    };
    app.on('framerender', onFrameRender);

    return () => {
        window.clearInterval(intervalId);
        app.off('framerender', onFrameRender);
    };
}

type SplatEntityProps = {
    scene: SceneConfig;
    onLoaded: () => void;
    onError: (error: string) => void;
    onProgress: (progress: number | null) => void;
};

function SplatEntity({ scene, onLoaded, onError, onProgress }: SplatEntityProps) {
    const activeAsset = scene.useLod && scene.lodAsset ? scene.lodAsset : scene.asset;
    const { asset, loading, error, subscribe } = useSplat(activeAsset);

    useEffect(() => {
        if (!subscribe) return;
        const unsubscribe = subscribe((meta) => {
            if (typeof meta?.progress === 'number') {
                onProgress(meta.progress);
            }
        });
        return () => {
            if (unsubscribe) unsubscribe();
        };
    }, [subscribe, onProgress]);

    useEffect(() => {
        if (error) {
            onError(typeof error === 'string' ? error : 'Failed to load spatial splat asset');
        } else if (asset && !loading) {
            onLoaded();
        }
    }, [asset, loading, error, onLoaded, onError]);

    if (!asset) return null;

    return (
        <Entity
            name={scene.name}
            position={scene.transform.position}
            rotation={scene.transform.rotation}
            scale={scene.transform.scale}
        >
            <GSplat asset={asset} unified={true} />
        </Entity>
    );
}

export type ViewerCanvasProps = {
    scene: SceneConfig;
    onLoaded: () => void;
    onError: (error: string) => void;
    onProgress: (progress: number | null) => void;
};

export const ViewerCanvas: React.FC<ViewerCanvasProps> = ({ scene, onLoaded, onError, onProgress }) => {
    const containerRef = useRef<HTMLDivElement>(null);

    const handleViewerClick = (e: React.MouseEvent) => {
        // Only trigger pointer lock if click was directly on the viewer/canvas
        if (
            (e.target as HTMLElement)?.closest('.ns-hud-header') ||
            (e.target as HTMLElement)?.closest('.ns-info-card') ||
            (e.target as HTMLElement)?.closest('.ns-editor-panel')
        ) {
            return;
        }
        const canvas = containerRef.current?.querySelector('canvas');
        if (canvas && document.pointerLockElement !== canvas) {
            canvas.requestPointerLock();
        }
    };

    // Clicking anywhere on the scene is a mouse shortcut only. Keyboard users start
    // mouse-look with the focusable "Click to explore" button rendered by App.tsx.
    return (
        <div ref={containerRef} className="ns-viewer-container" role="presentation" onClick={handleViewerClick}>
            <Application
                deviceTypes={[DEVICETYPE_WEBGPU, DEVICETYPE_WEBGL2]}
                // Splats are alpha-blended point sprites; without MSAA their edges
                // alias and read as "soft"/shimmery detail loss at any distance.
                graphicsDeviceOptions={{ antialias: true, powerPreference: 'high-performance' }}
                className="ns-playcanvas-canvas"
            >
                {/* Sharp when the GPU has headroom, lighter when it doesn't */}
                <AdaptiveResolution />

                {/* Native GSplat budget and LOD budget mode configuration */}
                <SplatBudgetConfigurator splatBudget={scene.splatBudget} splatBudgetMode={scene.splatBudgetMode} />

                {/* Camera positioned at eye level with first-person navigation */}
                <Entity name="camera" position={scene.camera.position}>
                    <Camera
                        clearColor={scene.camera.clearColor || '#0c0d12'}
                        fov={scene.camera.fov}
                        // 10 cm personal-space clip: 3DGS floaters often hover
                        // right on the lens and read as white/dark rings.
                        nearClip={0.1}
                        farClip={1000}
                    />
                    <Script
                        script={FirstPersonControls}
                        navigation={scene.navigation}
                        bounds={scene.bounds}
                        initialPosition={scene.camera.position}
                        initialRotation={scene.camera.rotation || [0, 0, 0]}
                        lookAtTarget={scene.camera.lookAt}
                    />
                </Entity>

                {/* 3D Gaussian Splat Entity */}
                <SplatEntity scene={scene} onLoaded={onLoaded} onError={onError} onProgress={onProgress} />
            </Application>
        </div>
    );
};
