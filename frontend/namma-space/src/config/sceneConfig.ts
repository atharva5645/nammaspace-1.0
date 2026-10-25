import type { SceneConfig } from '../types/scene';

/**
 * NammaSpace Scene Configuration
 *
 * Holds the spatial configuration for the digital twin scene.
 * Structured to be seamlessly loadable from a future backend API (e.g. GET /api/scenes/:id).
 */
export const defaultSceneConfig: SceneConfig = {
    id: 'room-001',
    name: 'Primary Spatial Twin (Native Octree LOD)',
    asset: '/room_fast.sog', // Untouched monolithic fallback
    lodAsset: '/room_lod/lod-meta.json', // Native PlayCanvas octree LOD manifest
    useLod: true, // Toggle between native streaming LOD and monolithic SOG
    splatBudget: 400000,
    splatBudgetMode: 'limit',

    // Verified transform values aligning room floor and leveling coordinate axes
    transform: {
        position: [0.46, -0.88, -0.49],
        rotation: [-57.22, -13.40, 24.30],
        scale: [1, 1, 1],
    },

    // Initial camera position and target framing the reconstructed scene
    camera: {
        position: [0, 0.2, 1.8],
        lookAt: [0.36, -0.46, -0.05],
        fov: 75,
        clearColor: '#0c0d12',
    },

    // First-person indoor spatial navigation parameters
    navigation: {
        mode: 'first-person',
        // In the aligned coordinate frame, the reconstructed floor sits at ~ Y = -1.4m.
        // A world Y elevation of 0.2m precisely corresponds to a 1.6m human eye-level walking height.
        eyeHeight: 0.2,
        movementSpeed: 2.2, // Walking speed in meters/second
        fastMovementSpeed: 4.2, // Sprint speed with Shift in meters/second
        lookSensitivity: 0.14, // Look sensitivity in degrees per mouse pixel
        pitchRange: [-85, 85], // Pitch clamp to prevent gimbal roll
        boundaryMargin: 0.20, // Snug perimeter margin (meters)
    },

    // Physical spatial bounding envelope expanded for unobstructed room walking
    bounds: {
        min: [-3.20, -2.96, -2.80],
        max: [3.20, 2.73, 3.40],
    },

    // Key interest points inside the digital twin
    waypoints: [
        {
            id: 'wp-center',
            name: 'Room Overview',
            position: [0, 0.2, 1.8],
            rotation: [0, 0, 0],
            description: 'Central perspective of the reconstructed room',
        },
    ],

    // Metadata describing capture pipeline and asset characteristics
    metadata: {
        splatFormat: 'SOG v3 (3 SH Bands)',
        gaussianCount: 476000,
        coordinateConvention: 'COLMAP Y-down / PlayCanvas Y-up',
        captureSource: 'gsplat 15k-step MCMC + 4cm Voxel Floater Culling',
        graphicsEngine: 'PlayCanvas 2.x WebGL/WebGPU',
        fidelity: 'High-Performance Spatial Twin (60+ FPS)',
    },
};
