export type Vec3Tuple = [number, number, number];

export type SceneTransform = {
    position: Vec3Tuple;
    rotation: Vec3Tuple;
    scale: Vec3Tuple;
};

export type CameraConfig = {
    position: Vec3Tuple;
    fov: number;
    clearColor?: string;
    rotation?: Vec3Tuple;
    lookAt?: Vec3Tuple;
};

export type SceneBounds = {
    min: Vec3Tuple;
    max: Vec3Tuple;
};

export type Waypoint = {
    id: string;
    name: string;
    position: Vec3Tuple;
    rotation?: Vec3Tuple;
    description?: string;
};

export type NavigationConfig = {
    mode: 'first-person' | 'camera-rail';
    eyeHeight: number;
    movementSpeed: number;
    fastMovementSpeed: number;
    lookSensitivity: number;
    pitchRange: [number, number];
    boundaryMargin: number;
    lookSmoothing?: number; // How fast the view follows the mouse (per second); higher = snappier
    railUrl?: string; // URL to camera rail JSON when mode === 'camera-rail'
};

export type SceneMetadata = {
    splatFormat?: string;
    gaussianCount?: number;
    coordinateConvention?: string;
    captureSource?: string;
    createdAt?: string;
    [key: string]: unknown;
};

export type SceneConfig = {
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
};
