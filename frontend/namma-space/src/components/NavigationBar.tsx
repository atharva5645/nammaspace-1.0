import React, { useState, useEffect } from 'react';

interface NavigationBarProps {
    onBackToWorkbench?: () => void;
    onToggleEditor?: () => void;
    isEditorOpen?: boolean;
    onReset?: () => void;
    onToggleInfo?: () => void;
    isInfoOpen?: boolean;
    currentSceneId?: string;
    onSelectScene?: (sceneId: string) => void;
}

export const NavigationBar: React.FC<NavigationBarProps> = ({
    onBackToWorkbench,
    onToggleEditor,
    isEditorOpen = false,
    onReset,
    onToggleInfo,
    isInfoOpen = false,
    currentSceneId = 'room-001',
    onSelectScene,
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

    const handleSceneChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        onSelectScene?.(event.target.value);
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
                {onToggleEditor && (
                    <button
                        type="button"
                        className={`ns-editor-mode-btn ${isEditorOpen ? 'active' : ''}`}
                        onClick={onToggleEditor}
                        aria-pressed={isEditorOpen}
                        aria-label={isEditorOpen ? 'Close Editor Mode' : 'Open Editor Mode'}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d="m15 5 4 4M4 20l4.5-1 10-10a2.12 2.12 0 0 0-3-3l-10 10L4 20Z" />
                            <path d="M13 7 17 11" />
                        </svg>
                        <span>{isEditorOpen ? 'Editing' : 'Editor Mode'}</span>
                    </button>
                )}
                {onBackToWorkbench && (
                    <button
                        type="button"
                        className="ns-hud-btn ns-back-to-workbench"
                        onClick={onBackToWorkbench}
                        title="Back to project setup"
                        aria-label="Back to project setup"
                    >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M19 12H5" />
                            <path d="m12 19-7-7 7-7" />
                        </svg>
                    </button>
                )}
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
                            <line x1="12" y1="16" x2="12" y2="8" />
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

                {/* Scene selector — switch between supermarket and hall */}
                <div className="ns-hud-waypoint">
                    <select
                        className="ns-hud-select"
                        onChange={handleSceneChange}
                        value={currentSceneId}
                        aria-label="Select scene"
                    >
                        <option value="playroom">Playroom (Hybrid)</option>
                        <option value="room-001">Room-001 Hall</option>
                        <option value="supermarket-001">Supermarket Aisle</option>
                    </select>
                </div>
            </div>
        </header>
    );
};
