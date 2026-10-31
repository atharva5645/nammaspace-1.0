import React, { useEffect, useRef } from 'react';
import { DEVICETYPE_WEBGPU, DEVICETYPE_WEBGL2 } from 'playcanvas';
import { Application, Entity } from '@playcanvas/react';
import { Camera, GSplat, Script } from '@playcanvas/react/components';
import { useSplat, useApp } from '@playcanvas/react/hooks';
import { FirstPersonControls } from '../controls/FirstPersonControls';
import type { SceneConfig } from '../types/scene';

/**
 * Balances high-DPI resolution and high performance to ensure silky smooth 60 FPS
 * navigation without crushing the GPU fill-rate on 1M+ Gaussian models.
 */
function HighDpiConfigurator() {
    const app = useApp();

    useEffect(() => {
        if (!app?.graphicsDevice) return;

        const updatePixelRatio = () => {
            // 1.25 provides sharp anti-aliased splats while saving ~60% GPU fillrate vs 2.5x/3x
            const dpr = Math.min(window.devicePixelRatio || 1, 1.25);
            if (app.graphicsDevice.maxPixelRatio !== dpr) {
                app.graphicsDevice.maxPixelRatio = dpr;
                app.resizeCanvas();
            }
        };

        updatePixelRatio();
        window.addEventListener('resize', updatePixelRatio);
        return () => window.removeEventListener('resize', updatePixelRatio);
    }, [app]);

    return null;
}

interface SplatBudgetConfiguratorProps {
    splatBudget?: number;
    splatBudgetMode?: 'limit' | 'target';
}

/**
 * Configures the native PlayCanvas GSplat budget balancer on app.scene.gsplat
 * and exposes live octree/LOD runtime telemetry on window.__namma_lod.
 */
function SplatBudgetConfigurator({
    splatBudget = 400000,
    splatBudgetMode = 'limit',
}: SplatBudgetConfiguratorProps) {
    const app = useApp();

    useEffect(() => {
        if (!app?.scene?.gsplat) return;

        app.scene.gsplat.splatBudget = splatBudget;
        app.scene.gsplat.splatBudgetMode = splatBudgetMode;

        // Periodic diagnostics sampler for live telemetry
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

            const director = (app as any).renderer?.gsplatDirector;
            let octreeCount = 0;
            let activeSplats = 0;
            let targetSplats = 0;
            let lod0Count = 0;
            let lod1Count = 0;
            let totalNodes = 0;
            const fileRefCounts: Record<string, number> = {};

            if (director?.camerasMap) {
                director.camerasMap.forEach((camData: any) => {
                    camData.layersMap?.forEach((layerData: any) => {
                        const world = layerData.gsplatManager?.world;
                        if (world?._octreeInstances) {
                            octreeCount += world._octreeInstances.size;
                            const state = world.getState?.(world.currentVersion);
                            if (state?.totalActiveSplats) {
                                activeSplats = Math.max(activeSplats, state.totalActiveSplats);
                            }
                            world._octreeInstances.forEach((inst: any) => {
                                if (inst.targetSplats) targetSplats = inst.targetSplats;
                                if (inst.activeSplats) activeSplats = Math.max(activeSplats, inst.activeSplats);
                                if (inst.nodeLods) {
                                    for (let i = 0; i < inst.nodeLods.length; i++) {
                                        totalNodes++;
                                        if (inst.nodeLods[i] === 0) lod0Count++;
                                        else if (inst.nodeLods[i] === 1) lod1Count++;
                                    }
                                }
                                if (inst.octree?.files && inst.octree?.fileRefCounts) {
                                    inst.octree.files.forEach((f: any, idx: number) => {
                                        fileRefCounts[f.url] = inst.octree.fileRefCounts[idx];
                                    });
                                }
                            });
                        }
                    });
                });
            }

            const loadedGsplatAssets = (app.assets as any)
                ?.filter((a: any) => a.type === 'gsplat' && a.loaded)
                ?.map((a: any) => a.file?.url || a.name) || [];

            (window as any).__namma_lod = {
                isLodActive: octreeCount > 0,
                octreeCount,
                activeSplats,
                targetSplats,
                splatBudget: app.scene.gsplat.splatBudget,
                splatBudgetMode: app.scene.gsplat.splatBudgetMode,
                nodeLodDistribution: { lod0: lod0Count, lod1: lod1Count, total: totalNodes },
                fileRefCounts,
                loadedChunks: loadedGsplatAssets,
                fps: currentFps,
                debugMode: app.scene.gsplat.debug,
                toggleDebugLod: (enable = true) => {
                    if (app?.scene?.gsplat) {
                        app.scene.gsplat.debug = enable ? 1 : 0;
                    }
                },
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
    }, [app, splatBudget, splatBudgetMode]);

    return null;
}

interface SplatEntityProps {
    scene: SceneConfig;
    onLoaded: () => void;
    onError: (error: string) => void;
    onProgress: (progress: number | null) => void;
}

function SplatEntity({ scene, onLoaded, onError, onProgress }: SplatEntityProps) {
    const activeAsset = (scene.useLod && scene.lodAsset) ? scene.lodAsset : scene.asset;
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

export interface ViewerCanvasProps {
    scene: SceneConfig;
    onLoaded: () => void;
    onError: (error: string) => void;
    onProgress: (progress: number | null) => void;
}

export const ViewerCanvas: React.FC<ViewerCanvasProps> = ({
    scene,
    onLoaded,
    onError,
    onProgress,
}) => {
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

    return (
        <div
            ref={containerRef}
            className="ns-viewer-container"
            onClick={handleViewerClick}
        >
            <Application
                deviceTypes={[DEVICETYPE_WEBGPU, DEVICETYPE_WEBGL2]}
                // Splats are alpha-blended point sprites; without MSAA their edges
                // alias and read as "soft"/shimmery detail loss at any distance.
                graphicsDeviceOptions={{ antialias: true, powerPreference: 'high-performance' }}
                className="ns-playcanvas-canvas"
            >
                {/* Ensure full 4K / Retina viewport pixel density */}
                <HighDpiConfigurator />

                {/* Native GSplat budget and LOD budget mode configuration */}
                <SplatBudgetConfigurator
                    splatBudget={scene.splatBudget}
                    splatBudgetMode={scene.splatBudgetMode}
                />

                {/* Camera positioned at eye level with first-person navigation */}
                <Entity
                    name="camera"
                    position={scene.camera.position}
                >
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
                <SplatEntity
                    scene={scene}
                    onLoaded={onLoaded}
                    onError={onError}
                    onProgress={onProgress}
                />
            </Application>
        </div>
    );
};
