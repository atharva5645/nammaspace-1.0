import type { SceneConfig, SceneTransform, Vec3Tuple } from '../types/scene';
import './editor-panel.css';
import './editor-toolbar-responsive.css';

interface EditorPanelProps {
    scene: SceneConfig;
    transform: SceneTransform;
    onTransformChange: (transform: SceneTransform) => void;
    onReset: () => void;
    onClose: () => void;
}

const axes = ['X', 'Y', 'Z'] as const;

function replaceAxis(vector: Vec3Tuple, index: number, value: number): Vec3Tuple {
    const next: Vec3Tuple = [...vector];
    next[index] = value;
    return next;
}

export function EditorPanel({ scene, transform, onTransformChange, onReset, onClose }: EditorPanelProps) {
    const isSplatOnly = scene.asset.endsWith('.sog') || scene.asset.endsWith('.ply');

    return (
        <aside className="ns-editor-panel" aria-label="Scene editor" onClick={(event) => event.stopPropagation()}>
            <header className="ns-editor-header">
                <div><span className="ns-editor-kicker">DEMO WORKSPACE</span><h2>Editor Mode</h2></div>
                <button type="button" className="ns-editor-close" onClick={onClose} aria-label="Close editor">×</button>
            </header>

            <div className="ns-editor-project"><span className="ns-editor-scene-icon">⌂</span><div><strong>{scene.id === 'room-001' ? 'Room-001 Hall' : scene.name}</strong><small>Demo scene · local preview</small></div><span className="ns-editor-status">PREVIEW</span></div>

            <section className="ns-editor-section">
                <div className="ns-editor-section-title"><div><span>01</span><h3>Model transform</h3></div><button type="button" onClick={onReset}>Reset</button></div>
                <p className="ns-editor-help">Position, rotate, and scale the whole captured model.</p>
                <div className="ns-transform-groups">
                    <TransformGroup label="Position" unit="u" values={transform.position} onChange={(index, value) => onTransformChange({ ...transform, position: replaceAxis(transform.position, index, value) })} />
                    <TransformGroup label="Rotation" unit="°" values={transform.rotation} onChange={(index, value) => onTransformChange({ ...transform, rotation: replaceAxis(transform.rotation, index, value) })} />
                </div>
                <label className="ns-uniform-scale">Uniform scale <span>{transform.scale[0].toFixed(2)}×</span><input aria-label="Uniform model scale" type="range" min="0.25" max="2.5" step="0.01" value={transform.scale[0]} onChange={(event) => { const value = Number(event.target.value); onTransformChange({ ...transform, scale: [value, value, value] }); }} /></label>
            </section>

            <section className="ns-editor-section ns-editor-selection">
                <div className="ns-editor-section-title"><div><span>02</span><h3>Scene layers</h3></div></div>
                <div className="ns-layer-row"><span className="ns-layer-eye">◉</span><span className="ns-layer-swatch"/><span className="ns-layer-name">Captured room</span><small>{isSplatOnly ? '3D scan' : '3D model'}</small></div>
                <div className="ns-editor-limit"><strong>What can be edited here?</strong><p>This demo is a captured 3D scan. You can adjust its overall transform. Editing individual walls, openings, or objects requires the editable wireframe stage.</p></div>
            </section>

            <section className="ns-editor-section ns-editor-next">
                <div className="ns-next-icon">✳</div><div><strong>Continue in the modelling workspace</strong><p>Precise wall and opening edits, review masks, and dimension constraints belong to the editable model workflow.</p></div>
            </section>

            <footer className="ns-editor-footer"><span>◉</span> Changes apply to this preview only and are not saved.</footer>
        </aside>
    );
}

function TransformGroup({ label, unit, values, onChange }: { label: string; unit: string; values: Vec3Tuple; onChange: (axis: number, value: number) => void }) {
    return (
        <fieldset className="ns-transform-group">
            <legend>{label}</legend>
            {axes.map((axis, index) => <label key={axis}><span>{axis}</span><input aria-label={`${label} ${axis}`} type="number" step={label === 'Rotation' ? 1 : 0.01} value={Number(values[index].toFixed(2))} onChange={(event) => onChange(index, Number(event.target.value))} /><small>{unit}</small></label>)}
        </fieldset>
    );
}
