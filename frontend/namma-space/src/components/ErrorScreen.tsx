import React from 'react';

interface ErrorScreenProps {
    message?: string | null;
    onRetry: () => void;
}

export const ErrorScreen: React.FC<ErrorScreenProps> = ({ message, onRetry }) => {
    return (
        <div className="ns-error-screen" role="alert">
            <div className="ns-error-card">
                <div className="ns-error-brand">
                    <span className="ns-brand-title">NammaSpace</span>
                    <span className="ns-brand-subtitle">Spatial Digital Twin</span>
                </div>

                <div className="ns-error-icon" aria-hidden="true">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="8" x2="12" y2="12" />
                        <line x1="12" y1="16" x2="12.01" y2="16" />
                    </svg>
                </div>

                <h2 className="ns-error-heading">Unable to load spatial scene.</h2>

                {message && (
                    <p className="ns-error-detail">{message}</p>
                )}

                <button
                    type="button"
                    className="ns-retry-button"
                    onClick={onRetry}
                >
                    Retry
                </button>
            </div>
        </div>
    );
};
