import type { Vec3Tuple, SceneTransform, CameraConfig, NavigationConfig, SceneBounds, Waypoint } from './scene';

/**
 * Capture-stage technical metadata
 */
export interface SceneCaptureMetadata {
    imageCount: number;
    resolution: string;
    rawResolution?: string;
    packageResolution?: string;
    cameraCount: number;
    sensor?: string;
    coverage?: string;
    notes?: string;
}

/**
 * COLMAP and 3D Gaussian Splatting reconstruction technical metadata
 */
export interface SceneReconstructionMetadata {
    method: string;
    registeredImages: number;
    sparsePoints: number;
    gaussians: number;
    shDegree: number;
    iterations?: number;
    trainingFramework?: string;
    bounds?: {
        min: Vec3Tuple;
        max: Vec3Tuple;
    };
    dimensions?: Vec3Tuple;
}

/**
 * Spatial LOD and render budget configuration
 */
export interface SceneRenderingMetadata {
    lodEnabled: boolean;
    splatBudget: number;
    splatBudgetMode?: 'limit' | 'target';
    initialDpr?: number;
    preferredApi?: Array<'WebGPU' | 'WebGL2'>;
}

/**
 * File asset paths for monolithic, streaming LOD, and fallback assets
 */
export interface SceneAssetMetadata {
    fallback: string;
    hq?: string;
    lod?: string;
    thumbnail?: string;
    preview?: string;
}

/**
 * Technical metrics describing the generated spatial LOD octree
 */
export interface SceneLodDetails {
    lodLevels?: number;
    octreeCount?: number;
    chunkCount?: number;
    totalChunkSize?: string;
    distribution?: string;
}

/**
 * Complete NammaSpace Scene Manifest structure
 */
export interface SceneManifest {
    id: string;
    name: string;
    type: 'indoor' | 'outdoor' | 'hybrid';
    description?: string;
    version?: string;

    capture: SceneCaptureMetadata;
    reconstruction: SceneReconstructionMetadata;
    rendering: SceneRenderingMetadata;
    assets: SceneAssetMetadata;
    lodDetails?: SceneLodDetails;

    transform: SceneTransform;
    camera: CameraConfig;
    navigation: NavigationConfig;
    bounds: SceneBounds;
    waypoints?: Waypoint[];
}

/**
 * Metric quality status
 */
export type QualityStatus = 'GOOD' | 'WARNING' | 'CRITICAL';

export interface QualityCategoryScore {
    status: QualityStatus;
    score: number; // 0 - 100
    metrics: Record<string, string | number | boolean>;
    warnings: string[];
}

export interface SceneQualityReport {
    sceneId: string;
    sceneName: string;
    generatedAt: string;

    overallStatus: QualityStatus;
    capture: QualityCategoryScore;
    reconstruction: QualityCategoryScore;
    lod: QualityCategoryScore;
    runtime: QualityCategoryScore;

    summaryWarnings: string[];
}
