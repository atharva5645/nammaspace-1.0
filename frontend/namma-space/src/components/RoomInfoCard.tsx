import React from 'react';
import type { SceneConfig } from '../types/scene';

interface RoomInfoCardProps {
    scene: SceneConfig;
    isOpen: boolean;
    onClose: () => void;
}

export const RoomInfoCard: React.FC<RoomInfoCardProps> = ({
    scene,
    isOpen,
    onClose,
}) => {
    if (!isOpen) return null;

    const gaussianCount =
        typeof scene.metadata.gaussianCount === 'number'
            ? scene.metadata.gaussianCount.toLocaleString()
            : '230,216';

    return (
        <aside
            className="ns-info-card"
            role="dialog"
            aria-label="Room Information"
            onClick={(e) => e.stopPropagation()}
            onPointerDown={(e) => e.stopPropagation()}
        >
            <div className="ns-info-header">
                <div>
                    <h2 className="ns-info-title">{scene.name}</h2>
                    <span className="ns-info-id">ID: {scene.id}</span>
                </div>
                <button
                    type="button"
                    className="ns-info-close"
                    onClick={(e) => {
                        e.stopPropagation();
                        onClose();
                    }}
                    aria-label="Close information"
                >
                    ✕
                </button>
            </div>

            <div className="ns-info-body">
                <div className="ns-info-row">
                    <span className="ns-info-label">Format</span>
                    <span className="ns-info-val">{scene.metadata.splatFormat || 'SOG v2'}</span>
                </div>
                <div className="ns-info-row">
                    <span className="ns-info-label">Gaussians</span>
                    <span className="ns-info-val">{gaussianCount}</span>
                </div>
                <div className="ns-info-row">
                    <span className="ns-info-label">Eye Height</span>
                    <span className="ns-info-val">{scene.navigation.eyeHeight}m (1.6m floor clearance)</span>
                </div>
                <div className="ns-info-row">
                    <span className="ns-info-label">Walk / Sprint</span>
                    <span className="ns-info-val">
                        {scene.navigation.movementSpeed}m/s · {scene.navigation.fastMovementSpeed}m/s
                    </span>
                </div>
                <div className="ns-info-row">
                    <span className="ns-info-label">Source</span>
                    <span className="ns-info-val">{String(scene.metadata.captureSource || 'Video Capture')}</span>
                </div>
                <div className="ns-info-row">
                    <span className="ns-info-label">Bounds</span>
                    <span className="ns-info-val ns-mono">
                        [{scene.bounds.min[0]}, {scene.bounds.min[1]}, {scene.bounds.min[2]}] to [{scene.bounds.max[0]}, {scene.bounds.max[1]}, {scene.bounds.max[2]}]
                    </span>
                </div>
            </div>
        </aside>
    );
};
