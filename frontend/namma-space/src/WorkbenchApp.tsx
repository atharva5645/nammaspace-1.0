import { lazy, Suspense, useState } from 'react';
import { ProjectIntake } from './workbench/ProjectIntake';

const ExistingViewer = lazy(() => import('./App'));

/** New project intake is the default product journey; the current viewer remains available. */
export default function WorkbenchApp() {
    const [showDemo, setShowDemo] = useState(() => {
        const params = new URLSearchParams(window.location.search);
        return params.has('scene') || params.get('view') === 'demo';
    });

    const openDemo = () => {
        const url = new URL(window.location.href);
        url.searchParams.set('view', 'demo');
        window.history.pushState({}, '', url.toString());
        setShowDemo(true);
    };

    const backToWorkbench = () => {
        const url = new URL(window.location.href);
        url.search = '';
        window.history.pushState({}, '', url.toString());
        setShowDemo(false);
    };

    if (showDemo) return <Suspense fallback={<div className="ns-app-loading">Opening demo scene…</div>}><ExistingViewer onBackToWorkbench={backToWorkbench} /></Suspense>;
    return <ProjectIntake onOpenDemo={openDemo} />;
}
