export type Vec3Tuple = [number, number, number];

export interface SceneTransform {
    position: Vec3Tuple;
    rotation: Vec3Tuple;
    scale: Vec3Tuple;
}

export interface CameraConfig {
    position: Vec3Tuple;
    fov: number;
    clearColor?: string;
    rotation?: Vec3Tuple;
    lookAt?: Vec3Tuple;
}

export interface SceneBounds {
    min: Vec3Tuple;
    max: Vec3Tuple;
}

export interface Waypoint {
    id: string;
    name: string;
    position: Vec3Tuple;
    rotation?: Vec3Tuple;
    description?: string;
}

export interface NavigationConfig {
    mode: 'first-person';
    eyeHeight: number;
    movementSpeed: number;
    fastMovementSpeed: number;
    lookSensitivity: number;
    pitchRange: [number, number];
    boundaryMargin: number;
}

export interface SceneMetadata {
    splatFormat?: string;
    gaussianCount?: number;
    coordinateConvention?: string;
    captureSource?: string;
    createdAt?: string;
    [key: string]: unknown;
}

export interface SceneConfig {
    id: string;
    name: string;
    asset: string;
    lodAsset?: string;
    useLod?: boolean;
    splatBudget?: number;
    splatBudgetMode?: 'limit' | 'target';
    transform: SceneTransform;
    camera: CameraConfig;
    navigation: NavigationConfig;
    bounds: SceneBounds;
    waypoints: Waypoint[];
    metadata: SceneMetadata;
}
