/**
 * CameraRailControls — Locks the PlayCanvas camera to the exact COLMAP training
 * camera poses. From these positions the 3DGS model renders identically to the
 * original dataset images because 3DGS was trained on exactly these viewpoints.
 *
 * Navigation:
 *   ArrowRight / D / scroll-down  → next waypoint
 *   ArrowLeft  / A / scroll-up    → previous waypoint
 *   Mouse drag                    → free-look around current position
 */

import * as pc from 'playcanvas';

export interface RailWaypoint {
    img: string;
    pos: [number, number, number];
    target: [number, number, number];
}

export interface RailConfig {
    waypoints: RailWaypoint[];
}

export class CameraRailControls {
    private entity: pc.Entity;
    private waypoints: RailWaypoint[] = [];
    private currentIndex: number = 0;
    private transitioning: boolean = false;
    private transitionT: number = 0;
    private transitionDuration: number = 0.6; // seconds

    // Transition state
    private fromPos: pc.Vec3 = new pc.Vec3();
    private toPos: pc.Vec3 = new pc.Vec3();
    private fromTarget: pc.Vec3 = new pc.Vec3();
    private toTarget: pc.Vec3 = new pc.Vec3();

    // Free-look offsets on top of rail camera
    private pitchOffset: number = 0;
    private yawOffset: number = 0;
    private maxLookOffset: number = 45; // degrees

    private isMouseDown: boolean = false;
    private lastMouseX: number = 0;
    private lastMouseY: number = 0;
    private lookSensitivity: number = 0.12;

    // Bound event handlers
    private onKeyDownBound = this.onKeyDown.bind(this);
    private onMouseDownBound = this.onMouseDown.bind(this);
    private onMouseUpBound = this.onMouseUp.bind(this);
    private onMouseMoveBound = this.onMouseMove.bind(this);
    private onWheelBound = this.onWheel.bind(this);

    constructor(entity: pc.Entity) {
        this.entity = entity;
    }

    public async loadRail(url: string): Promise<void> {
        const resp = await fetch(url);
        const data: RailConfig = await resp.json();
        this.waypoints = data.waypoints;
        console.log(`[CameraRail] Loaded ${this.waypoints.length} waypoints from ${url}`);
    }

    public initialize(): void {
        if (this.waypoints.length === 0) {
            console.warn('[CameraRail] No waypoints loaded');
            return;
        }

        // Snap to first waypoint immediately
        this.snapToWaypoint(this.currentIndex);

        // Bind inputs
        window.addEventListener('keydown', this.onKeyDownBound);
        window.addEventListener('mousedown', this.onMouseDownBound);
        window.addEventListener('mouseup', this.onMouseUpBound);
        window.addEventListener('mousemove', this.onMouseMoveBound);
        window.addEventListener('wheel', this.onWheelBound, { passive: true });

        this.dispatchIndexEvent();
    }

    public destroy(): void {
        window.removeEventListener('keydown', this.onKeyDownBound);
        window.removeEventListener('mousedown', this.onMouseDownBound);
        window.removeEventListener('mouseup', this.onMouseUpBound);
        window.removeEventListener('mousemove', this.onMouseMoveBound);
        window.removeEventListener('wheel', this.onWheelBound);
    }

    private snapToWaypoint(index: number): void {
        const wp = this.waypoints[index];
        this.entity.setPosition(wp.pos[0], wp.pos[1], wp.pos[2]);
        this.entity.lookAt(new pc.Vec3(wp.target[0], wp.target[1], wp.target[2]));
        this.pitchOffset = 0;
        this.yawOffset = 0;
    }

    private startTransition(toIndex: number): void {
        if (this.transitioning) return;
        if (toIndex < 0 || toIndex >= this.waypoints.length) return;

        const from = this.waypoints[this.currentIndex];
        const to = this.waypoints[toIndex];

        this.fromPos.set(from.pos[0], from.pos[1], from.pos[2]);
        this.toPos.set(to.pos[0], to.pos[1], to.pos[2]);
        this.fromTarget.set(from.target[0], from.target[1], from.target[2]);
        this.toTarget.set(to.target[0], to.target[1], to.target[2]);

        this.currentIndex = toIndex;
        this.transitioning = true;
        this.transitionT = 0;
        this.pitchOffset = 0;
        this.yawOffset = 0;
        this.dispatchIndexEvent();
    }

    private dispatchIndexEvent(): void {
        window.dispatchEvent(new CustomEvent('cameraRail:change', {
            detail: {
                index: this.currentIndex,
                total: this.waypoints.length,
                img: this.waypoints[this.currentIndex]?.img,
            }
        }));
    }

    public goNext(): void {
        if (this.currentIndex < this.waypoints.length - 1) {
            this.startTransition(this.currentIndex + 1);
        }
    }

    public goPrev(): void {
        if (this.currentIndex > 0) {
            this.startTransition(this.currentIndex - 1);
        }
    }

    public goTo(index: number): void {
        if (index >= 0 && index < this.waypoints.length) {
            this.startTransition(index);
        }
    }

    public get index(): number { return this.currentIndex; }
    public get total(): number { return this.waypoints.length; }

    // Called every frame from the parent component
    public update(dt: number): void {
        if (this.transitioning) {
            this.transitionT += dt / this.transitionDuration;
            if (this.transitionT >= 1) {
                this.transitionT = 1;
                this.transitioning = false;
            }

            // Smooth cubic ease-in-out
            const t = this.easeInOut(this.transitionT);
            const pos = new pc.Vec3().lerp(this.fromPos, this.toPos, t);
            const target = new pc.Vec3().lerp(this.fromTarget, this.toTarget, t);

            this.entity.setPosition(pos);
            this.entity.lookAt(target);
        }
    }

    private easeInOut(t: number): number {
        return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
    }

    private onKeyDown(e: KeyboardEvent): void {
        if ((e.target as HTMLElement)?.tagName === 'INPUT') return;
        if (e.code === 'ArrowRight' || e.code === 'KeyD') {
            this.goNext();
        } else if (e.code === 'ArrowLeft' || e.code === 'KeyA') {
            this.goPrev();
        }
    }

    private onMouseDown(e: MouseEvent): void {
        if ((e.target as HTMLElement)?.closest('.ns-hud-header') ||
            (e.target as HTMLElement)?.closest('.ns-info-card')) return;
        this.isMouseDown = true;
        this.lastMouseX = e.clientX;
        this.lastMouseY = e.clientY;
    }

    private onMouseUp(): void {
        this.isMouseDown = false;
    }

    private onMouseMove(e: MouseEvent): void {
        if (!this.isMouseDown || this.transitioning) return;
        const dx = e.clientX - this.lastMouseX;
        const dy = e.clientY - this.lastMouseY;
        this.lastMouseX = e.clientX;
        this.lastMouseY = e.clientY;

        this.yawOffset   -= dx * this.lookSensitivity;
        this.pitchOffset -= dy * this.lookSensitivity;

        this.yawOffset   = Math.max(-this.maxLookOffset, Math.min(this.maxLookOffset, this.yawOffset));
        this.pitchOffset = Math.max(-this.maxLookOffset, Math.min(this.maxLookOffset, this.pitchOffset));

        if (!this.transitioning) {
            const wp = this.waypoints[this.currentIndex];
            this.entity.setPosition(wp.pos[0], wp.pos[1], wp.pos[2]);
            this.entity.lookAt(new pc.Vec3(wp.target[0], wp.target[1], wp.target[2]));
            this.entity.rotateLocal(this.pitchOffset, this.yawOffset, 0);
        }
    }

    private onWheel(e: WheelEvent): void {
        if (e.deltaY > 0) this.goNext();
        else this.goPrev();
    }
}
