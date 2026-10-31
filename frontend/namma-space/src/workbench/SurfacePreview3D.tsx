import { useEffect, useRef, useState } from 'react';
import { Color, Entity as PcEntity, Mesh, MeshInstance, StandardMaterial } from 'playcanvas';
import { Application, Entity } from '@playcanvas/react';
import { Camera, Light, Script } from '@playcanvas/react/components';
import { useApp } from '@playcanvas/react/hooks';
import { DEVICETYPE_WEBGPU, DEVICETYPE_WEBGL2 } from 'playcanvas';
import { PreviewOrbitControls } from '../controls/PreviewOrbitControls';
import './surface-preview.css';

type PlyData = { positions: Float32Array; normals: Float32Array | null; colors: Uint8Array | null; indices: Uint32Array };
const scalarTypes: Record<string, { bytes: number; read: (view: DataView, offset: number) => number }> = {
    char: { bytes: 1, read: (v, o) => v.getInt8(o) }, int8: { bytes: 1, read: (v, o) => v.getInt8(o) },
    uchar: { bytes: 1, read: (v, o) => v.getUint8(o) }, uint8: { bytes: 1, read: (v, o) => v.getUint8(o) },
    short: { bytes: 2, read: (v, o) => v.getInt16(o, true) }, int16: { bytes: 2, read: (v, o) => v.getInt16(o, true) },
    ushort: { bytes: 2, read: (v, o) => v.getUint16(o, true) }, uint16: { bytes: 2, read: (v, o) => v.getUint16(o, true) },
    int: { bytes: 4, read: (v, o) => v.getInt32(o, true) }, int32: { bytes: 4, read: (v, o) => v.getInt32(o, true) },
    uint: { bytes: 4, read: (v, o) => v.getUint32(o, true) }, uint32: { bytes: 4, read: (v, o) => v.getUint32(o, true) },
    float: { bytes: 4, read: (v, o) => v.getFloat32(o, true) }, float32: { bytes: 4, read: (v, o) => v.getFloat32(o, true) },
    double: { bytes: 8, read: (v, o) => v.getFloat64(o, true) }, float64: { bytes: 8, read: (v, o) => v.getFloat64(o, true) },
};

async function parsePly(url: string): Promise<PlyData> {
    const buffer = await (await fetch(url)).arrayBuffer();
    const bytes = new Uint8Array(buffer);
    const headerEnd = new TextDecoder().decode(bytes.subarray(0, Math.min(bytes.length, 128 * 1024))).match(/end_header\r?\n/);
    if (!headerEnd || headerEnd.index === undefined) throw new Error('The surface file has an invalid PLY header.');
    const headerBytes = new TextEncoder().encode(headerEnd[0]).length;
    const dataOffset = headerEnd.index + headerBytes;
    const header = new TextDecoder().decode(bytes.subarray(0, dataOffset)).replace(/\r/g, '');
    const format = header.match(/^format (\S+)/m)?.[1];
    const vertexCount = Number(header.match(/^element vertex (\d+)/m)?.[1] || 0);
    const faceCount = Number(header.match(/^element face (\d+)/m)?.[1] || 0);
    const vertexSection = header.match(/^element vertex \d+\n([\s\S]*?)(?=^element |^end_header)/m)?.[1] || '';
    const properties = [...vertexSection.matchAll(/^property (\S+) (\S+)$/gm)].map((match) => ({ type: match[1], name: match[2] }));
    if (!vertexCount || !faceCount || !properties.some((property) => property.name === 'x') || !properties.some((property) => property.name === 'y') || !properties.some((property) => property.name === 'z')) throw new Error('The PLY file does not contain a triangle surface.');
    const vertices = new Float32Array(vertexCount * 3);
    const normals = ['nx', 'ny', 'nz'].every((name) => properties.some((property) => property.name === name)) ? new Float32Array(vertexCount * 3) : null;
    const hasColors = ['red', 'green', 'blue'].every((name) => properties.some((property) => property.name === name));
    const colors = hasColors ? new Uint8Array(vertexCount * 3) : null;
    const faces: number[] = [];
    if (format === 'ascii') {
        const lines = new TextDecoder().decode(bytes.subarray(dataOffset)).trim().split(/\r?\n/);
        for (let i = 0; i < vertexCount; i++) {
            const values = lines[i].trim().split(/\s+/).map(Number);
            properties.forEach((property, p) => {
                const target = property.name === 'x' ? vertices : property.name === 'y' ? vertices : property.name === 'z' ? vertices : null;
                const axis = property.name === 'x' ? 0 : property.name === 'y' ? 1 : property.name === 'z' ? 2 : -1;
                if (target && axis >= 0) target[i * 3 + axis] = values[p];
                if (normals && ['nx', 'ny', 'nz'].includes(property.name)) normals[i * 3 + ['nx', 'ny', 'nz'].indexOf(property.name)] = values[p];
                if (colors && ['red', 'green', 'blue'].includes(property.name)) colors[i * 3 + ['red', 'green', 'blue'].indexOf(property.name)] = values[p];
            });
        }
        for (let i = vertexCount; i < vertexCount + faceCount; i++) {
            const values = lines[i].trim().split(/\s+/).map(Number);
            const list = values.slice(1, 1 + values[0]);
            for (let p = 1; p + 1 < list.length; p++) faces.push(list[0], list[p], list[p + 1]);
        }
    } else if (format === 'binary_little_endian') {
        const view = new DataView(buffer);
        let offset = dataOffset;
        for (let i = 0; i < vertexCount; i++) {
            for (const property of properties) {
                const scalar = scalarTypes[property.type];
                if (!scalar) throw new Error(`Unsupported PLY value type: ${property.type}`);
                const value = scalar.read(view, offset); offset += scalar.bytes;
                const axis = ['x', 'y', 'z'].indexOf(property.name);
                const normalAxis = ['nx', 'ny', 'nz'].indexOf(property.name);
                const colorAxis = ['red', 'green', 'blue'].indexOf(property.name);
                if (axis >= 0) vertices[i * 3 + axis] = value;
                if (normals && normalAxis >= 0) normals[i * 3 + normalAxis] = value;
                if (colors && colorAxis >= 0) colors[i * 3 + colorAxis] = value;
            }
        }
        const faceSection = header.split(/^element face \d+\s*$/m)[1]?.split(/^element |^end_header/m)[0] || '';
        const listProperty = faceSection.match(/^property list (\S+) (\S+) (\S+)$/m);
        if (!listProperty) throw new Error('The PLY surface does not have indexed triangle faces.');
        const countType = scalarTypes[listProperty[1]], indexType = scalarTypes[listProperty[2]];
        if (!countType || !indexType) throw new Error('The PLY face index type is not supported.');
        for (let i = 0; i < faceCount; i++) {
            const count = countType.read(view, offset); offset += countType.bytes;
            const polygon: number[] = [];
            for (let j = 0; j < count; j++) { polygon.push(indexType.read(view, offset)); offset += indexType.bytes; }
            for (let j = 1; j + 1 < polygon.length; j++) faces.push(polygon[0], polygon[j], polygon[j + 1]);
        }
    } else throw new Error('The surface encoding is not supported by this viewer.');
    if (!faces.length) throw new Error('The surface file contains no renderable triangles.');
    let minX = Infinity, minY = Infinity, minZ = Infinity, maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    for (let i = 0; i < vertices.length; i += 3) { minX = Math.min(minX, vertices[i]); minY = Math.min(minY, vertices[i + 1]); minZ = Math.min(minZ, vertices[i + 2]); maxX = Math.max(maxX, vertices[i]); maxY = Math.max(maxY, vertices[i + 1]); maxZ = Math.max(maxZ, vertices[i + 2]); }
    const scale = 4 / Math.max(maxX - minX, maxY - minY, maxZ - minZ, 0.001);
    const center = [(minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2];
    for (let i = 0; i < vertices.length; i += 3) { vertices[i] = (vertices[i] - center[0]) * scale; vertices[i + 1] = (vertices[i + 1] - center[1]) * scale; vertices[i + 2] = (vertices[i + 2] - center[2]) * scale; }
    return { positions: vertices, normals, colors, indices: Uint32Array.from(faces) };
}

function SurfaceMesh({ src, onError }: { src: string; onError: (message: string) => void }) {
    const app = useApp();
    const entityRef = useRef<import('playcanvas').Entity | null>(null);
    useEffect(() => {
        if (!app?.graphicsDevice) return;
        let cancelled = false;
        let mesh: Mesh | null = null;
        let material: StandardMaterial | null = null;
        void parsePly(src).then((data) => {
            if (cancelled) return;
            mesh = new Mesh(app.graphicsDevice);
            mesh.setPositions(data.positions);
            if (data.normals) mesh.setNormals(data.normals);
            if (data.colors) mesh.setColors(data.colors, 3);
            mesh.setIndices(data.indices);
            mesh.update();
            material = new StandardMaterial();
            material.diffuse = new Color(1, 1, 1);
            material.diffuseVertexColor = Boolean(data.colors);
            material.useLighting = true;
            material.update();
            const instance = new MeshInstance(mesh, material);
            const entity = new PcEntity('reconstructed-room-surface');
            entity.addComponent('render', { meshInstances: [instance] });
            app.scene.root.addChild(entity);
            entityRef.current = entity;
        }).catch((error: unknown) => { if (!cancelled) onError(error instanceof Error ? error.message : 'Could not load this surface mesh.'); });
        return () => { cancelled = true; entityRef.current?.destroy(); entityRef.current = null; mesh?.destroy(); material?.destroy(); };
    }, [app, src, onError]);
    return null;
}

export function SurfacePreview3D({ src }: { src: string }) {
    const [error, setError] = useState('');
    return <div className="ns-surface-preview" aria-label="Interactive reconstructed 3D surface">
        <Application deviceTypes={[DEVICETYPE_WEBGPU, DEVICETYPE_WEBGL2]} graphicsDeviceOptions={{ antialias: true, powerPreference: 'high-performance' }}>
            <Entity name="surface-preview-camera" position={[5, 3.7, 5]}><Camera clearColor="#f4f0eb" fov={38} nearClip={0.01} farClip={1000} /><Script script={PreviewOrbitControls} pivot={[0, 0, 0]} /></Entity>
            <Entity name="surface-preview-key" rotation={[35, 25, 0]}><Light type="directional" /></Entity>
            <Entity name="surface-preview-fill" rotation={[20, -140, 0]}><Light type="directional" /></Entity>
            <SurfaceMesh src={src} onError={setError} />
        </Application>
        <div className="ns-surface-hint">Drag to orbit · Scroll to zoom</div>
        {error && <div className="ns-surface-error" role="alert">{error}</div>}
    </div>;
}
