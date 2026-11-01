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
        scale: [1, 1, 1]
    },

    // Camera spawns standing upright in the open walkway corridor looking down the aisle
    camera: {
        position: [0.0, 0.22, 1.8],
        lookAt: [0.0, 0.22, -2.5],
        fov: 65,
        clearColor: '#0c0d12'
    },

    // First-person indoor navigation calibrated to normalized aisle coordinates
    navigation: {
        mode: 'first-person',
        eyeHeight: 0.22,
        movementSpeed: 0.12, // Calm, smooth walking speed
        fastMovementSpeed: 0.28, // Sprint speed with Shift
        lookSensitivity: 0.1, // Smooth mouse look
        pitchRange: [-85, 85],
        boundaryMargin: 0.05
    },

    // Bounding envelope covering the complete walkway and grocery shelf units
    bounds: {
        min: [-2.0, 0.05, -7.0],
        max: [2.0, 1.5, 2.5]
    },

    waypoints: [
        {
            id: 'wp-aisle-entrance',
            name: 'Aisle Walkway Entrance',
            position: [0.0, 0.22, 1.8],
            rotation: [0, 0, 0],
            description: 'Standing at the start of the supermarket grocery aisle looking straight down the corridor'
        },
        {
            id: 'wp-aisle-mid',
            name: 'Mid-Aisle Walkway',
            position: [0.0, 0.22, -0.8],
            rotation: [0, 0, 0],
            description: 'Walking halfway down the aisle flanked by grocery shelves and packaged goods'
        },
        {
            id: 'wp-shelves-hq',
            name: 'Grocery Shelves (High-Res Packaging)',
            position: [0.45, 0.35, -3.4],
            rotation: [0, -90, 0],
            description:
                'Direct view of packaged grocery goods with crisp labels and price tags from an optimal viewing distance'
        }
    ],

    metadata: {
        splatFormat: 'SOG v3 (3 SH Bands)',
        gaussianCount: 486031,
        coordinateConvention: 'Precision-Leveled Ground Plane (Y-up, aisle -Z)',
        captureSource: 'Supermarket 15k-step Gradient 3DGS',
        graphicsEngine: 'PlayCanvas 2.x WebGL/WebGPU',
        fidelity: 'High-Fidelity Leveled Digital Twin (60 FPS)'
    }
};

/**
 * Demo Room Digital Twin (Room-001)
 */
export const defaultSceneConfig: SceneConfig = {
    id: 'room-001',
    name: 'Primary Spatial Twin (Native Octree LOD)',
    // Full-detail file used if LOD streaming is turned off
    // room_hq.sog with floaters and dark haze removed (original kept alongside)
    asset: '/room_hq_clean.sog',
    lodAsset: '/room_lod/lod-meta.json',
    // Off so the cleaned file is shown; the LOD stream still has the haze
    useLod: false,
    // LOD level 0 holds 475,674 splats. The old 400k limit forced parts of the
    // room down to the coarse level; 500k lets the whole room render at full detail.
    splatBudget: 500000,
    splatBudgetMode: 'limit',

    transform: {
        position: [0.46, -0.88, -0.49],
        rotation: [-57.22, -13.4, 24.3],
        scale: [1, 1, 1]
    },

    // Spawn facing the yellow corner with the sofa and table (pose matched to a
    // user-chosen screenshot: yaw 194 deg, pitch -22 deg)
    camera: {
        position: [-0.56, 0.23, -0.133],
        lookAt: [-0.336, -0.143, 0.767],
        fov: 75,
        clearColor: '#0c0d12'
    },

    navigation: {
        mode: 'first-person',
        eyeHeight: 0.2,
        movementSpeed: 0.15,
        fastMovementSpeed: 0.38,
        lookSensitivity: 0.14,
        pitchRange: [-85, 85],
        boundaryMargin: 0.2
    },

    bounds: {
        min: [-3.2, -2.96, -2.8],
        max: [3.2, 2.73, 3.4]
    },

    waypoints: [
        {
            id: 'wp-center',
            name: 'Room Overview',
            position: [0, 0.2, 1.8],
            rotation: [0, 0, 0],
            description: 'Central perspective of the reconstructed room'
        }
    ],

    metadata: {
        splatFormat: 'SOG v3 (3 SH Bands)',
        gaussianCount: 476000,
        coordinateConvention: 'COLMAP Y-down / PlayCanvas Y-up',
        captureSource: 'gsplat 15k-step MCMC + 4cm Voxel Floater Culling',
        graphicsEngine: 'PlayCanvas 2.x WebGL/WebGPU',
        fidelity: 'High-Performance Spatial Twin (60+ FPS)'
    }
};

/**
 * Playroom (Inria "Deep Blending" public dataset) built with the hybrid pipeline:
 * COLMAP photogrammetry depth maps carve smoke out of a gsplat MCMC splat, then
 * pipeline/tools/clean_splat.py. Leveled by pipeline/tools/level_splat.py, so the
 * floor is Y = 0, up is +Y and units are roughly metres.
 */
export const playroomSceneConfig: SceneConfig = {
    id: 'playroom',
    name: 'Playroom (Hybrid: Photogrammetry + Splat)',
    asset: '/scenes/playroom/scene.sog',
    useLod: false,
    splatBudget: 1000000,
    splatBudgetMode: 'limit',

    transform: {
        position: [0, 0, 0],
        rotation: [0, 0, 0],
        scale: [1, 1, 1]
    },

    camera: {
        position: [0, 1.62, 0],
        lookAt: [0, 1.3, -1],
        fov: 70,
        clearColor: '#0c0d12'
    },

    navigation: {
        mode: 'first-person',
        eyeHeight: 1.62,
        movementSpeed: 0.9,
        fastMovementSpeed: 1.8,
        lookSensitivity: 0.12,
        pitchRange: [-85, 85],
        boundaryMargin: 0.25
    },

    bounds: {
        min: [-2.03, -0.01, -1.77],
        max: [1.69, 2.61, 1.61]
    },

    waypoints: [
        {
            id: 'wp-playroom-centre',
            name: 'Room Centre',
            position: [0, 1.62, 0],
            rotation: [0, 0, 0],
            description: 'Middle of the playroom'
        }
    ],

    metadata: {
        splatFormat: 'SOG (3 SH bands)',
        coordinateConvention: 'Leveled: Y-up, floor at Y = 0',
        captureSource: 'Inria Deep Blending "playroom", gsplat 7k MCMC + depth loss, hybrid carving',
        graphicsEngine: 'PlayCanvas 2.x WebGL/WebGPU'
    }
};
