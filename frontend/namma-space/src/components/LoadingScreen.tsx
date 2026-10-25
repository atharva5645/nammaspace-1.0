import React from 'react';

interface LoadingScreenProps {
    progress?: number | null;
}

export const LoadingScreen: React.FC<LoadingScreenProps> = ({ progress }) => {
    const hasValidProgress =
        typeof progress === 'number' &&
        !Number.isNaN(progress) &&
        progress > 0 &&
        progress <= 1;

    const percentage = hasValidProgress ? Math.round(progress * 100) : null;

    return (
        <div className="ns-loading-screen" role="status" aria-live="polite">
            <div className="ns-loading-card">
                <div className="ns-loading-brand">
                    <span className="ns-brand-title">NammaSpace</span>
                    <span className="ns-brand-subtitle">Spatial Digital Twin</span>
                </div>

                <div className="ns-loader-indicator">
                    {hasValidProgress ? (
                        <div className="ns-progress-track">
                            <div
                                className="ns-progress-fill"
                                style={{ width: `${percentage}%` }}
                            />
                        </div>
                    ) : (
                        <div className="ns-spinner-indeterminate" aria-label="Loading animation" />
                    )}
                </div>

                <p className="ns-loading-message">Loading spatial scene...</p>

                {hasValidProgress && (
                    <span className="ns-progress-text">{percentage}%</span>
                )}
            </div>
        </div>
    );
};
