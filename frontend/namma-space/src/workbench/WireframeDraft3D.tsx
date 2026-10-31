import { useEffect, useMemo } from 'react';
import { Color, StandardMaterial } from 'playcanvas';
import { Application, Entity } from '@playcanvas/react';
import { Camera, Light, Render, Script } from '@playcanvas/react/components';
import { DEVICETYPE_WEBGPU, DEVICETYPE_WEBGL2 } from 'playcanvas';
import { PreviewOrbitControls } from '../controls/PreviewOrbitControls';
import type { WireframeDraft } from '../services/intakeApi';
import './wireframe-preview.css';

type Segment = { id: string; position: [number, number, number]; scale: [number, number, number]; kind: string };

function buildSegments(model: WireframeDraft): Segment[] {
    const nodes = new Map(model.nodes.map((node) => [node.id, node.position]));
    return model.edges.flatMap((edge) => {
        const a = nodes.get(edge.start), b = nodes.get(edge.end);
        if (!a || !b) return [];
        const dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
        const thickness = 0.025;
        return [{ id: edge.id, position: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2],
            scale: [Math.max(Math.abs(dx), thickness), Math.max(Math.abs(dy), thickness), Math.max(Math.abs(dz), thickness)], kind: edge.kind } as Segment];
    });
}

function DraftGeometry({ model }: { model: WireframeDraft }) {
    const materials = useMemo(() => {
        const wall = new StandardMaterial();
        wall.diffuse = new Color(0.67, 0.35, 0.18); wall.emissive = new Color(0.12, 0.045, 0.018); wall.useLighting = false; wall.update();
        const opening = new StandardMaterial();
        opening.diffuse = new Color(0.17, 0.52, 0.43); opening.emissive = new Color(0.03, 0.12, 0.09); opening.useLighting = false; opening.update();
        const grid = new StandardMaterial();
        grid.diffuse = new Color(0.82, 0.77, 0.7); grid.emissive = new Color(0.08, 0.065, 0.05); grid.useLighting = false; grid.update();
        const floor = new StandardMaterial(); floor.diffuse = new Color(0.93, 0.9, 0.86); floor.useLighting = false; floor.update();
        return { wall, opening, grid, floor };
    }, []);
    useEffect(() => () => { materials.wall.destroy(); materials.opening.destroy(); materials.grid.destroy(); materials.floor.destroy(); }, [materials]);
    const segments = useMemo(() => buildSegments(model), [model]);
    const xs = model.nodes.map((node) => node.position[0]), ys = model.nodes.map((node) => node.position[1]), zs = model.nodes.map((node) => node.position[2]);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minZ = Math.min(...zs), maxZ = Math.max(...zs);
    const centerX = (minX + maxX) / 2, centerZ = (minZ + maxZ) / 2;
    const span = Math.max(maxX - minX, maxZ - minZ, 2);
    const gridSize = span * 1.5, gridStep = span / 10;
    const grid = Array.from({ length: 11 }, (_, i) => -gridSize / 2 + i * gridStep).flatMap((offset, i) => [
        { id: `grid-x-${i}`, position: [centerX + offset, 0.006, centerZ] as [number, number, number], scale: [0.008, 0.008, gridSize] as [number, number, number] },
        { id: `grid-z-${i}`, position: [centerX, 0.006, centerZ + offset] as [number, number, number], scale: [gridSize, 0.008, 0.008] as [number, number, number] },
    ]);
    const cameraDistance = span * 1.45 + Math.max(...ys) * 0.4;

    return <div className="ns-wireframe-preview ns-wireframe-draft-preview" aria-label="Interactive dimensioned room wireframe">
        <Application deviceTypes={[DEVICETYPE_WEBGPU, DEVICETYPE_WEBGL2]} graphicsDeviceOptions={{ antialias: true, powerPreference: 'low-power' }}>
            <Entity name="draft-camera" position={[centerX + cameraDistance * 0.72, Math.max(...ys) * 1.1 + cameraDistance * 0.48, centerZ + cameraDistance * 0.8]}>
                <Camera clearColor="#f4f0eb" fov={35} nearClip={0.1} farClip={cameraDistance * 10} />
                <Script script={PreviewOrbitControls} pivot={[centerX, Math.max(...ys) / 2, centerZ]} minDistance={Math.max(1, span * 0.45)} maxDistance={Math.max(12, span * 5)} />
            </Entity>
            <Entity name="draft-floor" position={[centerX, -0.01, centerZ]} scale={[gridSize, 1, gridSize]}><Render type="plane" material={materials.floor} /></Entity>
            {grid.map((segment) => <Entity key={segment.id} {...segment}><Render type="box" material={materials.grid} /></Entity>)}
            {segments.map((segment) => <Entity key={segment.id} name={segment.id} position={segment.position} scale={segment.scale}><Render type="box" material={segment.kind === 'opening' ? materials.opening : materials.wall} /></Entity>)}
            {model.nodes.map((node) => <Entity key={node.id} name={node.id} position={node.position} scale={[0.07, 0.07, 0.07]}><Render type="sphere" material={node.id.startsWith('opening-') ? materials.opening : materials.wall} /></Entity>)}
            <Entity name="draft-key-light" rotation={[35, 25, 0]}><Light type="directional" /></Entity>
            <Entity name="draft-fill-light" rotation={[20, -140, 0]}><Light type="directional" /></Entity>
        </Application>
        <div className="ns-preview-controls-hint"><span>Drag to orbit</span><i>·</i><span>Scroll to zoom</span></div>
    </div>;
}

export function WireframeDraft3D({ model }: { model: WireframeDraft }) { return <DraftGeometry model={model} />; }
