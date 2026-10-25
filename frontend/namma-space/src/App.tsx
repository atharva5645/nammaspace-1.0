import React, { useState, useEffect, useCallback } from 'react';
import { defaultSceneConfig } from './config/sceneConfig';
import { ViewerCanvas } from './components/ViewerCanvas';
import { LoadingScreen } from './components/LoadingScreen';
import { ErrorScreen } from './components/ErrorScreen';
import { NavigationBar } from './components/NavigationBar';
import { RoomInfoCard } from './components/RoomInfoCard';

export const App: React.FC = () => {
    const [scene] = useState(defaultSceneConfig);
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [progress, setProgress] = useState<number | null>(null);
    const [retryKey, setRetryKey] = useState<number>(0);
    const [isInfoOpen, setIsInfoOpen] = useState<boolean>(false);
    const [isPointerLocked, setIsPointerLocked] = useState<boolean>(false);

    useEffect(() => {
        const handlePointerLockEvent = (e: Event) => {
            const detail = (e as CustomEvent)?.detail;
            setIsPointerLocked(Boolean(detail?.isLocked));
        };

        window.addEventListener('nammaspace:pointerlock', handlePointerLockEvent);
        return () => {
            window.removeEventListener('nammaspace:pointerlock', handlePointerLockEvent);
        };
    }, []);

    const handleLoaded = useCallback(() => {
        setIsLoading(false);
        setError(null);
    }, []);

    const handleError = useCallback((errorMessage: string) => {
        setIsLoading(false);
        setError(errorMessage);
    }, []);

    const handleProgress = useCallback((prog: number | null) => {
        setProgress(prog);
    }, []);

    const handleRetry = useCallback(() => {
        setError(null);
        setIsLoading(true);
        setProgress(null);
        setRetryKey((prev) => prev + 1);
    }, []);

    const toggleInfo = useCallback(() => {
        setIsInfoOpen((prev) => !prev);
    }, []);

    const closeInfo = useCallback(() => {
        setIsInfoOpen(false);
    }, []);

    const handleReset = useCallback(() => {
        window.dispatchEvent(
            new CustomEvent('nammaspace:reset', {
                detail: {
                    position: scene.camera.position,
                    lookAt: scene.camera.lookAt,
                },
            })
        );
    }, [scene.camera.position, scene.camera.lookAt]);

    const handleExploreClick = useCallback(() => {
        const canvas = document.querySelector('canvas');
        if (canvas && document.pointerLockElement !== canvas) {
            canvas.requestPointerLock();
        }
    }, []);

    return (
        <main className="ns-app-root">
            {/* PlayCanvas Spatial Digital Twin Viewer */}
            <ViewerCanvas
                key={retryKey}
                scene={scene}
                onLoaded={handleLoaded}
                onError={handleError}
                onProgress={handleProgress}
            />

            {/* Minimal HUD overlay */}
            <NavigationBar
                onReset={handleReset}
                onToggleInfo={toggleInfo}
                isInfoOpen={isInfoOpen}
            />

            {/* Room Information drawer */}
            <RoomInfoCard
                scene={scene}
                isOpen={isInfoOpen}
                onClose={closeInfo}
            />

            {/* Subtle "Click to explore" navigation hint */}
            {!isLoading && !error && !isPointerLocked && (
                <div
                    className="ns-explore-prompt"
                    onClick={handleExploreClick}
                    role="button"
                    tabIndex={0}
                    aria-label="Click to explore spatial scene"
                >
                    <span className="ns-prompt-pill">Click to enter FPS look (or drag to look)</span>
                    <span className="ns-prompt-keys">WASD to walk · Shift to sprint · Esc to exit</span>
                </div>
            )}

            {/* Loading experience */}
            {isLoading && !error && (
                <LoadingScreen progress={progress} />
            )}

            {/* Error fallback state */}
            {error && (
                <ErrorScreen
                    message={error}
                    onRetry={handleRetry}
                />
            )}
        </main>
    );
};

export default App;
