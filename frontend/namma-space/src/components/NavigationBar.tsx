import React, { useState, useEffect } from 'react';

interface NavigationBarProps {
    onReset?: () => void;
    onToggleInfo?: () => void;
    isInfoOpen?: boolean;
}

export const NavigationBar: React.FC<NavigationBarProps> = ({
    onReset,
    onToggleInfo,
    isInfoOpen = false,
}) => {
    const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

    useEffect(() => {
        const handleFullscreenChange = () => {
            setIsFullscreen(Boolean(document.fullscreenElement));
        };

        document.addEventListener('fullscreenchange', handleFullscreenChange);
        return () => {
            document.removeEventListener('fullscreenchange', handleFullscreenChange);
        };
    }, []);

    const toggleFullscreen = async (e: React.MouseEvent) => {
        e.stopPropagation();
        try {
            if (!document.fullscreenElement) {
                await document.documentElement.requestFullscreen();
            } else {
                await document.exitFullscreen();
            }
        } catch (err) {
            console.error('Fullscreen request error:', err);
        }
    };

    const handleResetClick = (e: React.MouseEvent) => {
        e.stopPropagation();
        onReset?.();
    };

    const handleInfoClick = (e: React.MouseEvent) => {
        e.stopPropagation();
        onToggleInfo?.();
    };

    return (
        <header
            className="ns-hud-header"
            onPointerDown={(e) => e.stopPropagation()}
        >
            {/* Minimal top-left HUD branding */}
            <div className="ns-hud-brand">
                <h1 className="ns-hud-title">NammaSpace</h1>
                <span className="ns-hud-tagline">Spatial Digital Twin</span>
            </div>

            {/* Subtle top-right controls */}
            <div className="ns-hud-actions">
                {onReset && (
                    <button
                        type="button"
                        className="ns-hud-btn"
                        onClick={handleResetClick}
                        title="Recenter Camera (Initial Perspective)"
                        aria-label="Recenter Camera"
                    >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                            <path d="M3 3v5h5" />
                        </svg>
                    </button>
                )}

                {onToggleInfo && (
                    <button
                        type="button"
                        className={`ns-hud-btn ${isInfoOpen ? 'active' : ''}`}
                        onClick={handleInfoClick}
                        title="Room Information"
                        aria-label="Toggle Room Information"
                    >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <circle cx="12" cy="12" r="10" />
                            <line x1="12" y1="16" x2="12" y2="12" />
                            <line x1="12" y1="8" x2="12.01" y2="8" />
                        </svg>
                    </button>
                )}

                <button
                    type="button"
                    className="ns-hud-btn"
                    onClick={toggleFullscreen}
                    title={isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen'}
                    aria-label={isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen'}
                >
                    {isFullscreen ? (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3" />
                        </svg>
                    ) : (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
                        </svg>
                    )}
                </button>
            </div>
        </header>
    );
};
