import { Script } from 'playcanvas';

import type { NavigationConfig, SceneBounds, Vec3Tuple } from '../types/scene';

/**
 * Computes exact Euler yaw and pitch angles in degrees to orient an upright camera (zero-roll)
 * from a given eye position towards a target position.
 */
/** Window event the on-screen up/down buttons send to the camera controls. */
export const VERTICAL_EVENT = 'nammaspace:vertical';
export type VerticalEventDetail = { direction: 'up' | 'down'; active: boolean };

export function computeLookAtAngles(eye: Vec3Tuple, target: Vec3Tuple): { yaw: number; pitch: number } {
    const dx = target[0] - eye[0];
    const dy = target[1] - eye[1];
    const dz = target[2] - eye[2];
    const dh = Math.hypot(dx, dz);

    const yaw = (Math.atan2(-dx, -dz) * 180) / Math.PI;
    const pitch = (Math.atan2(dy, dh) * 180) / Math.PI;

    return { yaw, pitch };
}

/** Signed difference to rotate from `from` to `to` degrees the short way (-180..180]. */
function shortestAngleDelta(from: number, to: number): number {
    return ((((to - from) % 360) + 540) % 360) - 180;
}

function easeInOutCubic(t: number): number {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/**
 * NammaSpace High-Performance Spatial Navigation Controller
 *
 * Implements dual-mode ultra-responsive controls:
 * 1. Pointer-Lock Mode: Click canvas to capture cursor for seamless FPS look
 * 2. Click-and-Drag Mode: Hold left or right click to orbit/look around without pointer lock
 * 3. Smooth Velocity-Based WASD: Acceleration & damping curves eliminate movement lag and jitter
 * 4. Independent Axis Sliding: Hitting an X boundary allows Z movement along the wall without freezing
 * 5. Splat Sorter Friendly: Skips matrix invalidation on sub-pixel micro-movements to avoid GPU sort thrashing
 */
export class FirstPersonControls extends Script {
    static scriptName = 'firstPersonControls';

    // Script properties passed from React / sceneConfig
    public navigation?: NavigationConfig;
    public bounds?: SceneBounds;
    public initialPosition: Vec3Tuple = [0, 0.2, 1.8];
    public initialRotation: Vec3Tuple = [0, 0, 0];
    public lookAtTarget?: Vec3Tuple;

    // Navigation configuration values (tuned for calm, precise surface exploration)
    public eyeHeight = 0.2;
    public movementSpeed = 0.1; // Gentle, steady exploration speed
    public fastMovementSpeed = 0.28; // Controlled sprint with Shift
    public lookSensitivity = 0.1;
    public pitchRange: [number, number] = [-85, 85];
    public boundaryMargin = 0.25;
    public speedMultiplier = 1.0;

    // How quickly the view catches up with the mouse (per second). Higher = snappier,
    // lower = smoother. ~20 removes jitter from uneven mouse events without feeling laggy.
    public lookSmoothing = 20;
    // Duration of animated camera moves for reset / waypoints, in seconds
    public transitionDuration = 0.9;

    // Orientation state in degrees. yaw/pitch is what is rendered; target* is where
    // the mouse wants the view to be, and the rendered angles ease toward it.
    private yaw = 0;
    private pitch = 0;
    private targetYaw = 0;
    private targetPitch = 0;
    private initialYaw = 0;
    private initialPitch = 0;

    // Active animated transition (reset / waypoint jump), if any
    private transition: {
        t: number;
        fromPos: [number, number, number];
        toPos: [number, number, number];
        fromYaw: number;
        toYaw: number;
        fromPitch: number;
        toPitch: number;
    } | null = null;

    // Movement velocity state for smooth inertia
    private velX = 0;
    private velY = 0;
    private velZ = 0;
    private currentY = 0;

    // Input state
    private isLocked = false;
    private isMouseDown = false;
    private lastMouseX = 0;
    private lastMouseY = 0;
    private keys = new Set<string>();
    private pendingDx = 0;
    private pendingDy = 0;

    // Bound listeners for cleanup
    private onKeyDownBound = this.onKeyDown.bind(this);
    private onKeyUpBound = this.onKeyUp.bind(this);
    private onMouseDownBound = this.onMouseDown.bind(this);
    private onMouseUpBound = this.onMouseUp.bind(this);
    private onMouseMoveBound = this.onMouseMove.bind(this);
    private onPointerLockChangeBound = this.onPointerLockChange.bind(this);
    private onWindowBlurBound = this.onWindowBlur.bind(this);
    private onVerticalEventBound = this.onVerticalEvent.bind(this);
    private onResetEventBound = this.onResetEvent.bind(this);

    initialize() {
        this.applyConfig();

        // Position camera firmly at human eye height or configured elevation
        const startPos = this.initialPosition;
        this.currentY = typeof startPos[1] === 'number' ? startPos[1] : this.eyeHeight;
        this.entity.setPosition(startPos[0], this.currentY, startPos[2]);

        // Derive initial orientation from lookAtTarget if configured, otherwise use initialRotation
        if (this.lookAtTarget) {
            const angles = computeLookAtAngles(startPos, this.lookAtTarget);
            this.yaw = angles.yaw;
            this.pitch = Math.max(this.pitchRange[0], Math.min(this.pitchRange[1], angles.pitch));
        } else {
            const currentRot = this.entity.getEulerAngles();
            this.pitch = currentRot.x || this.initialRotation[0] || 0;
            this.yaw = currentRot.y || this.initialRotation[1] || 0;
        }

        this.initialYaw = this.yaw;
        this.initialPitch = this.pitch;
        this.targetYaw = this.yaw;
        this.targetPitch = this.pitch;

        // Apply starting orientation (roll remains strictly 0)
        this.entity.setEulerAngles(this.pitch, this.yaw, 0);

        // Bind global input handlers
        window.addEventListener('keydown', this.onKeyDownBound);
        window.addEventListener('keyup', this.onKeyUpBound);
        window.addEventListener('blur', this.onWindowBlurBound);
        window.addEventListener('nammaspace:reset', this.onResetEventBound);
        window.addEventListener(VERTICAL_EVENT, this.onVerticalEventBound);
        window.addEventListener('mousedown', this.onMouseDownBound);
        window.addEventListener('mouseup', this.onMouseUpBound);
        window.addEventListener('mousemove', this.onMouseMoveBound);
        document.addEventListener('pointerlockchange', this.onPointerLockChangeBound);

        // Check if pointer lock is already active
        this.onPointerLockChange();
    }

    private applyConfig() {
        if (!this.navigation) return;

        if (typeof this.navigation.eyeHeight === 'number') {
            this.eyeHeight = this.navigation.eyeHeight;
        }
        if (typeof this.navigation.movementSpeed === 'number') {
            this.movementSpeed = this.navigation.movementSpeed;
        }
        if (typeof this.navigation.fastMovementSpeed === 'number') {
            this.fastMovementSpeed = this.navigation.fastMovementSpeed;
        }
        if (typeof this.navigation.lookSensitivity === 'number') {
            this.lookSensitivity = this.navigation.lookSensitivity;
        }
        if (Array.isArray(this.navigation.pitchRange)) {
            this.pitchRange = this.navigation.pitchRange;
        }
        if (typeof this.navigation.boundaryMargin === 'number') {
            this.boundaryMargin = this.navigation.boundaryMargin;
        }
        if (typeof this.navigation.lookSmoothing === 'number') {
            this.lookSmoothing = this.navigation.lookSmoothing;
        }
    }

    private onKeyDown(e: KeyboardEvent) {
        // Typing in a field or using a dropdown (e.g. the scene selector) must not move the camera
        const tag = (e.target as HTMLElement)?.tagName;
        if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;

        // Space (up) would otherwise scroll the page or "click" the focused HUD button
        if (e.code === 'Space') e.preventDefault();

        this.keys.add(e.code);

        // Runtime speed tuning: [ or - slows down, ] or + speeds up
        if (e.code === 'BracketLeft' || e.code === 'Minus') {
            this.speedMultiplier = Math.max(0.15, this.speedMultiplier * 0.75);
        } else if (e.code === 'BracketRight' || e.code === 'Equal') {
            this.speedMultiplier = Math.min(3.0, this.speedMultiplier * 1.35);
        }

        // If Escape is pressed, release pointer lock
        if (e.code === 'Escape' && document.pointerLockElement) {
            document.exitPointerLock();
        }
    }

    private onKeyUp(e: KeyboardEvent) {
        this.keys.delete(e.code);
    }

    private onMouseDown(e: MouseEvent) {
        // Ignore clicks on HUD buttons or Drawer cards
        if (
            (e.target as HTMLElement)?.closest('.ns-hud-header') ||
            (e.target as HTMLElement)?.closest('.ns-info-card') ||
            (e.target as HTMLElement)?.closest('.ns-editor-panel') ||
            (e.target as HTMLElement)?.closest('.ns-vertical-controls')
        ) {
            return;
        }

        this.isMouseDown = true;
        this.lastMouseX = e.clientX;
        this.lastMouseY = e.clientY;
    }

    private onMouseUp() {
        this.isMouseDown = false;
    }

    /** On-screen up/down buttons: held = moving, released = stop. */
    private onVerticalEvent(e: Event) {
        const detail = (e as CustomEvent<VerticalEventDetail>).detail;
        if (!detail) return;
        const key = detail.direction === 'up' ? 'VirtualUp' : 'VirtualDown';
        if (detail.active) this.keys.add(key);
        else this.keys.delete(key);
    }

    private onWindowBlur() {
        this.keys.clear();
        this.isMouseDown = false;
        this.velX = 0;
        this.velZ = 0;
    }

    private onPointerLockChange() {
        const canvas = this.app?.graphicsDevice?.canvas;
        this.isLocked = Boolean(canvas && document.pointerLockElement === canvas);

        // Notify application
        window.dispatchEvent(
            new CustomEvent('nammaspace:pointerlock', {
                detail: { isLocked: this.isLocked }
            })
        );
    }

    private onMouseMove(e: MouseEvent) {
        if (this.isLocked) {
            // Pointer lock mode: accumulate standard movement deltas
            this.pendingDx += e.movementX || 0;
            this.pendingDy += e.movementY || 0;
        } else if (this.isMouseDown) {
            // Drag-to-look mode: user is dragging mouse on canvas
            const dx = e.clientX - this.lastMouseX;
            const dy = e.clientY - this.lastMouseY;
            this.lastMouseX = e.clientX;
            this.lastMouseY = e.clientY;

            // Damp drag speed slightly for comfortable precision
            this.pendingDx += dx * 1.1;
            this.pendingDy += dy * 1.1;
        }
    }

    private onResetEvent(e: Event) {
        const detail = (e as CustomEvent)?.detail;
        this.reset(detail?.position, detail?.yaw, detail?.pitch, detail?.lookAt);
    }

    /** Animates the camera to a position/orientation (used by reset and waypoints). */
    public reset(position?: Vec3Tuple, yaw?: number, pitch?: number, lookAt?: Vec3Tuple) {
        const targetPos = position || this.initialPosition;
        const targetLookAt = lookAt || this.lookAtTarget;

        let toYaw: number;
        let toPitch: number;
        if (typeof yaw === 'number' && typeof pitch === 'number') {
            toYaw = yaw;
            toPitch = pitch;
        } else if (targetLookAt) {
            const angles = computeLookAtAngles(targetPos, targetLookAt);
            toYaw = angles.yaw;
            toPitch = angles.pitch;
        } else {
            toYaw = this.initialYaw;
            toPitch = this.initialPitch;
        }
        toPitch = Math.max(this.pitchRange[0], Math.min(this.pitchRange[1], toPitch));
        // Turn the short way round instead of spinning through 300+ degrees
        toYaw = this.yaw + shortestAngleDelta(this.yaw, toYaw);

        this.pendingDx = 0;
        this.pendingDy = 0;
        this.velX = 0;
        this.velY = 0;
        this.velZ = 0;
        this.keys.clear();

        const p = this.entity.getPosition();
        const toY = typeof targetPos[1] === 'number' ? targetPos[1] : this.eyeHeight;
        this.transition = {
            t: 0,
            fromPos: [p.x, p.y, p.z],
            toPos: [targetPos[0], toY, targetPos[2]],
            fromYaw: this.yaw,
            toYaw,
            fromPitch: this.pitch,
            toPitch
        };
    }

    /** Advances an active transition. Returns true while the camera is being animated. */
    private stepTransition(dt: number): boolean {
        const tr = this.transition;
        if (!tr) return false;

        tr.t = Math.min(1, tr.t + dt / Math.max(0.01, this.transitionDuration));
        const k = easeInOutCubic(tr.t);
        const x = tr.fromPos[0] + (tr.toPos[0] - tr.fromPos[0]) * k;
        const y = tr.fromPos[1] + (tr.toPos[1] - tr.fromPos[1]) * k;
        const z = tr.fromPos[2] + (tr.toPos[2] - tr.fromPos[2]) * k;
        this.yaw = tr.fromYaw + (tr.toYaw - tr.fromYaw) * k;
        this.pitch = tr.fromPitch + (tr.toPitch - tr.fromPitch) * k;
        this.targetYaw = this.yaw;
        this.targetPitch = this.pitch;
        this.currentY = y;

        this.entity.setPosition(x, y, z);
        this.entity.setEulerAngles(this.pitch, this.yaw, 0);

        if (tr.t >= 1) this.transition = null;
        return true;
    }

    update(dt: number) {
        const clampedDt = Math.min(dt, 0.05);

        // 0. Animated reset / waypoint move takes over until it finishes,
        //    unless the user starts moving, which cancels it where it is.
        if (this.transition) {
            const userInput = this.keys.size > 0 || Math.abs(this.pendingDx) > 2 || Math.abs(this.pendingDy) > 2;
            if (userInput) {
                this.transition = null;
            } else {
                this.pendingDx = 0;
                this.pendingDy = 0;
                this.stepTransition(clampedDt);
                return;
            }
        }

        // 1. Buffered mouse deltas move the *target* view direction
        if (this.pendingDx !== 0 || this.pendingDy !== 0) {
            this.targetYaw -= this.pendingDx * this.lookSensitivity;
            this.targetPitch -= this.pendingDy * this.lookSensitivity;
            this.pendingDx = 0;
            this.pendingDy = 0;
            // Clamp pitch to avoid gimbal flip
            this.targetPitch = Math.max(this.pitchRange[0], Math.min(this.pitchRange[1], this.targetPitch));
        }

        // 1b. Rendered view eases toward the target (frame-rate independent smoothing)
        const dYaw = this.targetYaw - this.yaw;
        const dPitch = this.targetPitch - this.pitch;
        if (Math.abs(dYaw) > 0.001 || Math.abs(dPitch) > 0.001) {
            const lookK = 1 - Math.exp(-this.lookSmoothing * clampedDt);
            this.yaw += dYaw * lookK;
            this.pitch += dPitch * lookK;
            if (Math.abs(this.targetYaw - this.yaw) < 0.001) this.yaw = this.targetYaw;
            if (Math.abs(this.targetPitch - this.pitch) < 0.001) this.pitch = this.targetPitch;
            this.entity.setEulerAngles(this.pitch, this.yaw, 0);
        }

        // 2. Read directional keyboard inputs
        const isForward = this.keys.has('KeyW') || this.keys.has('ArrowUp');
        const isBackward = this.keys.has('KeyS') || this.keys.has('ArrowDown');
        const isLeft = this.keys.has('KeyA') || this.keys.has('ArrowLeft');
        const isRight = this.keys.has('KeyD') || this.keys.has('ArrowRight');
        // Up/down: keyboard, or the on-screen buttons (VERTICAL_EVENT -> Virtual* keys)
        const isUp = this.keys.has('Space') || this.keys.has('KeyE') || this.keys.has('VirtualUp');
        const isDown = this.keys.has('KeyC') || this.keys.has('KeyQ') || this.keys.has('VirtualDown');

        // Determine walk vs sprint speed, dynamically evaluating current scene navigation config
        const baseSpeed =
            typeof this.navigation?.movementSpeed === 'number' ? this.navigation.movementSpeed : this.movementSpeed;
        const sprintSpeed =
            typeof this.navigation?.fastMovementSpeed === 'number'
                ? this.navigation.fastMovementSpeed
                : this.fastMovementSpeed;

        const isShift = this.keys.has('ShiftLeft') || this.keys.has('ShiftRight');
        const targetSpeed = (isShift ? sprintSpeed : baseSpeed) * this.speedMultiplier;

        // Project horizontal forward and right vectors
        const forward = this.entity.forward;
        const right = this.entity.right;

        const fwdLen = Math.hypot(forward.x, forward.z) || 1;
        const hFwdX = forward.x / fwdLen;
        const hFwdZ = forward.z / fwdLen;

        const rightLen = Math.hypot(right.x, right.z) || 1;
        const hRightX = right.x / rightLen;
        const hRightZ = right.z / rightLen;

        let inputX = 0;
        let inputZ = 0;

        if (isForward) {
            inputX += hFwdX;
            inputZ += hFwdZ;
        }
        if (isBackward) {
            inputX -= hFwdX;
            inputZ -= hFwdZ;
        }
        if (isRight) {
            inputX += hRightX;
            inputZ += hRightZ;
        }
        if (isLeft) {
            inputX -= hRightX;
            inputZ -= hRightZ;
        }

        const inputLen = Math.hypot(inputX, inputZ);
        let targetVelX = 0;
        let targetVelZ = 0;

        if (inputLen > 0) {
            targetVelX = (inputX / inputLen) * targetSpeed;
            targetVelZ = (inputZ / inputLen) * targetSpeed;
        }

        let targetVelY = 0;
        if (isUp) targetVelY += targetSpeed * 0.75;
        if (isDown) targetVelY -= targetSpeed * 0.75;

        // 3. Smooth velocity acceleration and deceleration curves.
        //    Exponential form keeps the feel identical at 30, 60 or 144 FPS.
        const accelRate = inputLen > 0 || isUp || isDown ? 8 : 10;
        const lerpFactor = 1 - Math.exp(-accelRate * clampedDt);
        this.velX += (targetVelX - this.velX) * lerpFactor;
        this.velY += (targetVelY - this.velY) * lerpFactor;
        this.velZ += (targetVelZ - this.velZ) * lerpFactor;

        const currentSpeed = Math.hypot(this.velX, this.velY, this.velZ);
        if (currentSpeed > 0.005) {
            const currentPos = this.entity.getPosition();
            let nextX = currentPos.x + this.velX * clampedDt;
            let nextY = (this.currentY || currentPos.y) + this.velY * clampedDt;
            let nextZ = currentPos.z + this.velZ * clampedDt;

            // 4. Independent Axis Sliding Collision with Room Boundaries
            if (this.bounds) {
                const minX = this.bounds.min[0] + this.boundaryMargin;
                const maxX = this.bounds.max[0] - this.boundaryMargin;
                const minY = this.bounds.min[1] + this.boundaryMargin;
                const maxY = this.bounds.max[1] - this.boundaryMargin;
                const minZ = this.bounds.min[2] + this.boundaryMargin;
                const maxZ = this.bounds.max[2] - this.boundaryMargin;

                // Slide along wall if one axis reaches bounds
                if (nextX < minX) {
                    nextX = minX;
                    this.velX = 0;
                } else if (nextX > maxX) {
                    nextX = maxX;
                    this.velX = 0;
                }

                if (nextY < minY) {
                    nextY = minY;
                    this.velY = 0;
                } else if (nextY > maxY) {
                    nextY = maxY;
                    this.velY = 0;
                }

                if (nextZ < minZ) {
                    nextZ = minZ;
                    this.velZ = 0;
                } else if (nextZ > maxZ) {
                    nextZ = maxZ;
                    this.velZ = 0;
                }
            }

            this.currentY = nextY;
            this.entity.setPosition(nextX, this.currentY, nextZ);
        }
    }

    destroy() {
        window.removeEventListener('keydown', this.onKeyDownBound);
        window.removeEventListener('keyup', this.onKeyUpBound);
        window.removeEventListener('blur', this.onWindowBlurBound);
        window.removeEventListener('nammaspace:reset', this.onResetEventBound);
        window.removeEventListener(VERTICAL_EVENT, this.onVerticalEventBound);
        window.removeEventListener('mousedown', this.onMouseDownBound);
        window.removeEventListener('mouseup', this.onMouseUpBound);
        window.removeEventListener('mousemove', this.onMouseMoveBound);
        document.removeEventListener('pointerlockchange', this.onPointerLockChangeBound);
    }
}
