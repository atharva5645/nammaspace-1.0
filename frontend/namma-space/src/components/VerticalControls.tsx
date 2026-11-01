import React, { useCallback, useEffect } from 'react';

import { VERTICAL_EVENT } from '../controls/FirstPersonControls';
import type { VerticalEventDetail } from '../controls/FirstPersonControls';

function send(direction: VerticalEventDetail['direction'], active: boolean) {
    window.dispatchEvent(new CustomEvent<VerticalEventDetail>(VERTICAL_EVENT, { detail: { direction, active } }));
}

/** Press-and-hold buttons to move the camera up and down (same as Space/E and Q/C). */
export const VerticalControls: React.FC = () => {
    // Make sure nothing keeps moving if the pointer is released outside a button
    useEffect(() => {
        const stopAll = () => {
            send('up', false);
            send('down', false);
        };
        window.addEventListener('pointerup', stopAll);
        window.addEventListener('pointercancel', stopAll);
        return () => {
            window.removeEventListener('pointerup', stopAll);
            window.removeEventListener('pointercancel', stopAll);
            stopAll();
        };
    }, []);

    const bind = useCallback(
        (direction: VerticalEventDetail['direction']) => ({
            onPointerDown: (e: React.PointerEvent) => {
                e.preventDefault();
                e.stopPropagation();
                send(direction, true);
            },
            onPointerUp: () => send(direction, false),
            onPointerLeave: () => send(direction, false),
            // Keyboard users: Enter/Space on the focused button moves while held
            onKeyDown: (e: React.KeyboardEvent) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    e.stopPropagation();
                    send(direction, true);
                }
            },
            onKeyUp: (e: React.KeyboardEvent) => {
                if (e.key === 'Enter' || e.key === ' ') send(direction, false);
            },
            onBlur: () => send(direction, false),
            onContextMenu: (e: React.MouseEvent) => e.preventDefault()
        }),
        []
    );

    return (
        <div className="ns-vertical-controls" role="group" aria-label="Move up or down">
            <button type="button" className="ns-hud-btn ns-vertical-btn" title="Move up (Space / E)" aria-label="Move up" {...bind('up')}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M6 15l6-6 6 6" />
                </svg>
            </button>
            <span className="ns-vertical-label" aria-hidden="true">Height</span>
            <button type="button" className="ns-hud-btn ns-vertical-btn" title="Move down (Q / C)" aria-label="Move down" {...bind('down')}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M6 9l6 6 6-6" />
                </svg>
            </button>
        </div>
    );
};
