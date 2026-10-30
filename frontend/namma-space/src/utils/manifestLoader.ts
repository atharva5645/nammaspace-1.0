import type { SceneManifest } from '../types/manifest';
import type { SceneConfig } from '../types/scene';

/**
 * Transforms a SceneManifest into a runtime SceneConfig consumed by PlayCanvas ViewerCanvas.
 * Ensures backward compatibility, fallback protection, and preserves native LOD streaming.
 */
export function manifestToSceneConfig(manifest: SceneManifest): SceneConfig {
    const useLod = manifest.rendering?.lodEnabled ?? true;
    const activeLodAsset = manifest.assets?.lod;
    const activeFallbackAsset = manifest.assets?.fallback || '/room_fast.sog';

    return {
        id: manifest.id,
        name: manifest.name,
        // When useLod is true and lod asset is available, ViewerCanvas selects lodAsset;
        // otherwise it falls back to the monolithic SOG asset.
        asset: activeFallbackAsset,
        lodAsset: activeLodAsset,
        useLod: useLod && Boolean(activeLodAsset),
        splatBudget: manifest.rendering?.splatBudget ?? 400000,
        splatBudgetMode: manifest.rendering?.splatBudgetMode ?? 'limit',

        transform: manifest.transform,
        camera: manifest.camera,
        navigation: manifest.navigation,
        bounds: manifest.bounds,
        waypoints: manifest.waypoints || [],

        metadata: {
            splatFormat: 'SOG v3 (3 SH Bands)',
            gaussianCount: manifest.reconstruction?.gaussians ?? 1000000,
            coordinateConvention: 'COLMAP Y-down / PlayCanvas Y-up',
            captureSource: manifest.reconstruction?.method || 'COLMAP + Gaussian Splatting',
            graphicsEngine: 'PlayCanvas 2.x WebGL/WebGPU',
            fidelity: manifest.rendering?.lodEnabled
                ? 'High-Performance Spatial Twin (Native Octree LOD, 60 FPS)'
                : 'High-Fidelity Monolithic Spatial Twin (1M Gaussians, 60 FPS)',
            manifest,
        },
    };
}

/**
 * Fetches and parses a SceneManifest from a public URL or API endpoint.
 */
export async function loadSceneManifest(manifestUrl: string): Promise<SceneManifest> {
    const res = await fetch(manifestUrl);
    if (!res.ok) {
        throw new Error(`Failed to load scene manifest from ${manifestUrl}: ${res.statusText}`);
    }
    const data = (await res.json()) as SceneManifest;
    if (!data.id || !data.capture || !data.reconstruction || !data.assets) {
        throw new Error(`Invalid scene manifest at ${manifestUrl}: missing required sections.`);
    }
    return data;
}
