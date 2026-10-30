import type { SceneConfig } from '../types/scene';

/**
 * Supermarket Aisle High-Fidelity Leveled Digital Twin
 *
 * Reconstructed with standard gradient-based 3DGS (15,000 steps)
 * leveled to horizontal floor plane, pruned floaters, and anti-needle clamped.
 */
export const supermarketSceneConfig: SceneConfig = {
    id: 'supermarket-001',
    name: 'Supermarket Aisle (Leveled Digital Twin)',
    asset: '/supermarket_hq_leveled.sog',
    useLod: false,
    splatBudget: 2000000,
    splatBudgetMode: 'target',

    transform: {
        position: [0, 0, 0],
        rotation: [0, 0, 0],
        scale: [1, 1, 1],
    },

    // Camera spawns standing upright in the open walkway corridor looking down the aisle
    camera: {
        position: [0.0, 0.22, 1.80],
        lookAt: [0.0, 0.22, -2.50],
        fov: 65,
        clearColor: '#0c0d12',
    },

    // First-person indoor navigation calibrated to normalized aisle coordinates
    navigation: {
        mode: 'first-person',
        eyeHeight: 0.22,
        movementSpeed: 0.12, // Calm, smooth walking speed
        fastMovementSpeed: 0.28, // Sprint speed with Shift
        lookSensitivity: 0.10, // Smooth mouse look
        pitchRange: [-85, 85],
        boundaryMargin: 0.05,
    },

    // Bounding envelope covering the complete walkway and grocery shelf units
    bounds: {
        min: [-2.00, 0.05, -7.00],
        max: [2.00, 1.50, 2.50],
    },

    waypoints: [
        {
            id: 'wp-aisle-entrance',
            name: 'Aisle Walkway Entrance',
            position: [0.0, 0.22, 1.80],
            rotation: [0, 0, 0],
            description: 'Standing at the start of the supermarket grocery aisle looking straight down the corridor',
        },
        {
            id: 'wp-aisle-mid',
            name: 'Mid-Aisle Walkway',
            position: [0.0, 0.22, -0.80],
            rotation: [0, 0, 0],
            description: 'Walking halfway down the aisle flanked by grocery shelves and packaged goods',
        },
        {
            id: 'wp-shelves-hq',
            name: 'Grocery Shelves (High-Res Packaging)',
            position: [0.45, 0.35, -3.40],
            rotation: [0, -90, 0],
            description: 'Direct view of packaged grocery goods with crisp labels and price tags from an optimal viewing distance',
        },
    ],

    metadata: {
        splatFormat: 'SOG v3 (3 SH Bands)',
        gaussianCount: 486031,
        coordinateConvention: 'Precision-Leveled Ground Plane (Y-up, aisle -Z)',
        captureSource: 'Supermarket 15k-step Gradient 3DGS',
        graphicsEngine: 'PlayCanvas 2.x WebGL/WebGPU',
        fidelity: 'High-Fidelity Leveled Digital Twin (60 FPS)',
    },
};

/**
 * Demo Room Digital Twin (Room-001)
 */
export const defaultSceneConfig: SceneConfig = {
    id: 'room-001',
    name: 'Primary Spatial Twin (Native Octree LOD)',
    asset: '/room_fast.sog',
    lodAsset: '/room_lod/lod-meta.json',
    useLod: true,
    splatBudget: 400000,
    splatBudgetMode: 'limit',

    transform: {
        position: [0.46, -0.88, -0.49],
        rotation: [-57.22, -13.40, 24.30],
        scale: [1, 1, 1],
    },

    camera: {
        position: [0, 0.2, 1.8],
        lookAt: [0.36, -0.46, -0.05],
        fov: 75,
        clearColor: '#0c0d12',
    },

    navigation: {
        mode: 'first-person',
        eyeHeight: 0.2,
        movementSpeed: 0.15,
        fastMovementSpeed: 0.38,
        lookSensitivity: 0.14,
        pitchRange: [-85, 85],
        boundaryMargin: 0.20,
    },

    bounds: {
        min: [-3.20, -2.96, -2.80],
        max: [3.20, 2.73, 3.40],
    },

    waypoints: [
        {
            id: 'wp-center',
            name: 'Room Overview',
            position: [0, 0.2, 1.8],
            rotation: [0, 0, 0],
            description: 'Central perspective of the reconstructed room',
        },
    ],

    metadata: {
        splatFormat: 'SOG v3 (3 SH Bands)',
        gaussianCount: 476000,
        coordinateConvention: 'COLMAP Y-down / PlayCanvas Y-up',
        captureSource: 'gsplat 15k-step MCMC + 4cm Voxel Floater Culling',
        graphicsEngine: 'PlayCanvas 2.x WebGL/WebGPU',
        fidelity: 'High-Performance Spatial Twin (60+ FPS)',
    },
};
