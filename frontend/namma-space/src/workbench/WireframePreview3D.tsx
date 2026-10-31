import { useEffect, useMemo } from 'react';
import { Color, StandardMaterial } from 'playcanvas';
import { Application, Entity } from '@playcanvas/react';
import { Camera, Light, Render, Script } from '@playcanvas/react/components';
import { DEVICETYPE_WEBGPU, DEVICETYPE_WEBGL2 } from 'playcanvas';
import { PreviewOrbitControls } from '../controls/PreviewOrbitControls';
import './wireframe-preview.css';

interface Segment {
    id: string;
    position: [number, number, number];
    scale: [number, number, number];
}

const roomWidth = 4.2;
const roomDepth = 3.2;
const roomHeight = 2.7;
const halfWidth = roomWidth / 2;
const halfDepth = roomDepth / 2;
const frameY = roomHeight / 2;
const tube = 0.024;

const roomSegments: Segment[] = [
    { id: 'floor-front', position: [0, 0.03, halfDepth], scale: [roomWidth, tube, tube] },
    { id: 'floor-back', position: [0, 0.03, -halfDepth], scale: [roomWidth, tube, tube] },
    { id: 'floor-left', position: [-halfWidth, 0.03, 0], scale: [tube, tube, roomDepth] },
    { id: 'floor-right', position: [halfWidth, 0.03, 0], scale: [tube, tube, roomDepth] },
    { id: 'ceiling-front', position: [0, roomHeight, halfDepth], scale: [roomWidth, tube, tube] },
    { id: 'ceiling-back', position: [0, roomHeight, -halfDepth], scale: [roomWidth, tube, tube] },
    { id: 'ceiling-left', position: [-halfWidth, roomHeight, 0], scale: [tube, tube, roomDepth] },
    { id: 'ceiling-right', position: [halfWidth, roomHeight, 0], scale: [tube, tube, roomDepth] },
    { id: 'corner-a', position: [-halfWidth, frameY, halfDepth], scale: [tube, roomHeight, tube] },
    { id: 'corner-b', position: [halfWidth, frameY, halfDepth], scale: [tube, roomHeight, tube] },
    { id: 'corner-c', position: [-halfWidth, frameY, -halfDepth], scale: [tube, roomHeight, tube] },
    { id: 'corner-d', position: [halfWidth, frameY, -halfDepth], scale: [tube, roomHeight, tube] },
];

const floorGrid: Segment[] = Array.from({ length: 11 }, (_, index) => {
    const offset = -2.5 + index * 0.5;
    return [
        { id: `grid-x-${index}`, position: [offset, 0.008, 0] as [number, number, number], scale: [0.008, 0.008, 4.4] as [number, number, number] },
        { id: `grid-z-${index}`, position: [0, 0.008, offset] as [number, number, number], scale: [5.4, 0.008, 0.008] as [number, number, number] },
    ];
}).flat();

const corners: [number, number, number][] = [
    [-halfWidth, 0.03, -halfDepth], [halfWidth, 0.03, -halfDepth],
    [-halfWidth, 0.03, halfDepth], [halfWidth, 0.03, halfDepth],
    [-halfWidth, roomHeight, -halfDepth], [halfWidth, roomHeight, -halfDepth],
    [-halfWidth, roomHeight, halfDepth], [halfWidth, roomHeight, halfDepth],
];

function PreviewMaterials() {
    const materials = useMemo(() => {
        const wire = new StandardMaterial();
        wire.diffuse = new Color(0.67, 0.35, 0.18);
        wire.emissive = new Color(0.12, 0.045, 0.018);
        wire.useLighting = false;
        wire.update();

        const grid = new StandardMaterial();
        grid.diffuse = new Color(0.82, 0.77, 0.7);
        grid.emissive = new Color(0.08, 0.065, 0.05);
        grid.useLighting = false;
        grid.update();

        const floor = new StandardMaterial();
        floor.diffuse = new Color(0.93, 0.9, 0.86);
        floor.useLighting = false;
        floor.update();
        return { wire, grid, floor };
    }, []);

    useEffect(() => () => {
        materials.wire.destroy();
        materials.grid.destroy();
        materials.floor.destroy();
    }, [materials]);

    return (
        <>
            <Entity name="preview-floor" position={[0, 0, 0]} scale={[5.4, 1, 4.4]}>
                <Render type="plane" material={materials.floor} />
            </Entity>
            {floorGrid.map((segment) => <Entity key={segment.id} name={segment.id} position={segment.position} scale={segment.scale}><Render type="box" material={materials.grid} /></Entity>)}
            {roomSegments.map((segment) => <Entity key={segment.id} name={segment.id} position={segment.position} scale={segment.scale}><Render type="box" material={materials.wire} /></Entity>)}
            {corners.map((position, index) => <Entity key={`corner-node-${index}`} name={`corner-node-${index}`} position={position} scale={[0.09, 0.09, 0.09]}><Render type="sphere" material={materials.wire} /></Entity>)}
            <Entity name="preview-key-light" rotation={[35, 25, 0]}><Light type="directional" /></Entity>
            <Entity name="preview-fill-light" rotation={[20, -140, 0]}><Light type="directional" /></Entity>
        </>
    );
}

export function WireframePreview3D() {
    return (
        <div className="ns-wireframe-preview" aria-label="Interactive three-dimensional room wireframe">
            <Application deviceTypes={[DEVICETYPE_WEBGPU, DEVICETYPE_WEBGL2]} graphicsDeviceOptions={{ antialias: true, powerPreference: 'low-power' }}>
                <Entity name="wireframe-preview-camera" position={[5.4, 4.4, 6.2]}>
                    <Camera clearColor="#f4f0eb" fov={34} nearClip={0.1} farClip={100} />
                    <Script script={PreviewOrbitControls} pivot={[0, 1.2, 0]} />
                </Entity>
                <PreviewMaterials />
            </Application>
            <div className="ns-preview-controls-hint"><span>Drag to orbit</span><i>·</i><span>Scroll to zoom</span></div>
        </div>
    );
}
