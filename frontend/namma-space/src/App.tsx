import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { supermarketSceneConfig, defaultSceneConfig, playroomSceneConfig } from './config/sceneConfig';
import { ViewerCanvas } from './components/ViewerCanvas';
import { LoadingScreen } from './components/LoadingScreen';
import { ErrorScreen } from './components/ErrorScreen';
import { NavigationBar } from './components/NavigationBar';
import { RoomInfoCard } from './components/RoomInfoCard';
import { EditorPanel } from './components/EditorPanel';
import { VerticalControls } from './components/VerticalControls';
import type { SceneConfig, SceneTransform } from './types/scene';

const SCENES: Record<string, SceneConfig> = {
    'room-001': defaultSceneConfig,
    'supermarket-001': supermarketSceneConfig,
    playroom: playroomSceneConfig
};

export interface ExistingViewerProps {
    onBackToWorkbench?: () => void;
}

export const App: React.FC<ExistingViewerProps> = ({ onBackToWorkbench }) => {
    // Read an explicit scene parameter; otherwise open the hybrid Playroom demo scene.
    const [activeSceneId, setActiveSceneId] = useState<string>(() => {
        if (typeof window !== 'undefined') {
            const params = new URLSearchParams(window.location.search);
            const sceneParam = params.get('scene');
            if (sceneParam && sceneParam in SCENES) {
                return sceneParam;
            }
        }
        return 'playroom';
    });

    const scene = useMemo(() => SCENES[activeSceneId] ?? defaultSceneConfig, [activeSceneId]);
    const [editorTransform, setEditorTransform] = useState<SceneTransform | null>(null);
    const [isEditorOpen, setIsEditorOpen] = useState(false);
    const displayedScene = useMemo(
        () => editorTransform ? { ...scene, transform: editorTransform } : scene,
        [scene, editorTransform]
    );

    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [progress, setProgress] = useState<number | null>(null);
    const [retryKey, setRetryKey] = useState<number>(0);
    const [isInfoOpen, setIsInfoOpen] = useState<boolean>(false);
    const [isPointerLocked, setIsPointerLocked] = useState<boolean>(false);

    const handleSelectScene = useCallback((newId: string) => {
        if (newId !== activeSceneId) {
            setIsLoading(true);
            setProgress(null);
            setError(null);
            setActiveSceneId(newId);
            setEditorTransform(null);
            setIsEditorOpen(false);
            setRetryKey((prev) => prev + 1);

            const url = new URL(window.location.href);
            url.searchParams.set('scene', newId);
            window.history.pushState({}, '', url.toString());
        }
    }, [activeSceneId]);

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

    const toggleEditor = useCallback(() => {
        if (!isEditorOpen && document.pointerLockElement) document.exitPointerLock();
        setIsEditorOpen((open) => !open);
        setIsInfoOpen(false);
    }, [isEditorOpen]);

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
                key={`${activeSceneId}-${retryKey}`}
                scene={displayedScene}
                onLoaded={handleLoaded}
                onError={handleError}
                onProgress={handleProgress}
            />

            {/* Minimal HUD overlay */}
            <NavigationBar
                onBackToWorkbench={onBackToWorkbench}
                onToggleEditor={toggleEditor}
                isEditorOpen={isEditorOpen}
                onReset={handleReset}
                onToggleInfo={toggleInfo}
                isInfoOpen={isInfoOpen}
                currentSceneId={activeSceneId}
                onSelectScene={handleSelectScene}
            />

            {/* Room Information drawer */}
            <RoomInfoCard
                scene={scene}
                isOpen={isInfoOpen}
                onClose={closeInfo}
            />

            {isEditorOpen && (
                <EditorPanel
                    scene={scene}
                    transform={displayedScene.transform}
                    onTransformChange={setEditorTransform}
                    onReset={() => setEditorTransform(null)}
                    onClose={() => setIsEditorOpen(false)}
                />
            )}

            {/* Up/down buttons, available in every scene */}
            {!isLoading && !error && <VerticalControls />}

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
                    <span className="ns-prompt-keys">WASD to walk · Space/E up · Q/C down · Shift to sprint · Esc to exit</span>
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
