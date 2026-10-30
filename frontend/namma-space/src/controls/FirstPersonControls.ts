import { Script } from 'playcanvas';
import type { NavigationConfig, SceneBounds, Vec3Tuple } from '../types/scene';

/**
 * Computes exact Euler yaw and pitch angles in degrees to orient an upright camera (zero-roll)
 * from a given eye position towards a target position.
 */
export function computeLookAtAngles(
    eye: Vec3Tuple,
    target: Vec3Tuple
): { yaw: number; pitch: number } {
    const dx = target[0] - eye[0];
    const dy = target[1] - eye[1];
    const dz = target[2] - eye[2];
    const dh = Math.hypot(dx, dz);

    const yaw = (Math.atan2(-dx, -dz) * 180) / Math.PI;
    const pitch = (Math.atan2(dy, dh) * 180) / Math.PI;

    return { yaw, pitch };
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
    public movementSpeed = 0.10; // Gentle, steady exploration speed
    public fastMovementSpeed = 0.28; // Controlled sprint with Shift
    public lookSensitivity = 0.10;
    public pitchRange: [number, number] = [-85, 85];
    public boundaryMargin = 0.25;
    public speedMultiplier = 1.0;

    // Orientation state in degrees
    private yaw = 0;
    private pitch = 0;
    private initialYaw = 0;
    private initialPitch = 0;

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
    private keys: Set<string> = new Set();
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

        // Apply starting orientation (roll remains strictly 0)
        this.entity.setEulerAngles(this.pitch, this.yaw, 0);

        // Bind global input handlers
        window.addEventListener('keydown', this.onKeyDownBound);
        window.addEventListener('keyup', this.onKeyUpBound);
        window.addEventListener('blur', this.onWindowBlurBound);
        window.addEventListener('nammaspace:reset', this.onResetEventBound);
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
    }

    private onKeyDown(e: KeyboardEvent) {
        if ((e.target as HTMLElement)?.tagName === 'INPUT') return;

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
        if ((e.target as HTMLElement)?.closest('.ns-hud-header') ||
            (e.target as HTMLElement)?.closest('.ns-info-card')) {
            return;
        }

        this.isMouseDown = true;
        this.lastMouseX = e.clientX;
        this.lastMouseY = e.clientY;
    }

    private onMouseUp() {
        this.isMouseDown = false;
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
                detail: { isLocked: this.isLocked },
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

    public reset(position?: Vec3Tuple, yaw?: number, pitch?: number, lookAt?: Vec3Tuple) {
        const targetPos = position || this.initialPosition;
        const targetLookAt = lookAt || this.lookAtTarget;

        this.pendingDx = 0;
        this.pendingDy = 0;
        this.velX = 0;
        this.velY = 0;
        this.velZ = 0;
        this.currentY = typeof targetPos[1] === 'number' ? targetPos[1] : this.eyeHeight;

        if (typeof yaw === 'number' && typeof pitch === 'number') {
            this.yaw = yaw;
            this.pitch = pitch;
        } else if (targetLookAt) {
            const angles = computeLookAtAngles(targetPos, targetLookAt);
            this.yaw = angles.yaw;
            this.pitch = Math.max(this.pitchRange[0], Math.min(this.pitchRange[1], angles.pitch));
        } else {
            this.yaw = this.initialYaw;
            this.pitch = this.initialPitch;
        }

        this.entity.setPosition(targetPos[0], this.currentY, targetPos[2]);
        this.entity.setEulerAngles(this.pitch, this.yaw, 0);
        this.keys.clear();
    }

    update(dt: number) {
        const clampedDt = Math.min(dt, 0.05);

        // 1. Process buffered mouse look deltas
        if (Math.abs(this.pendingDx) > 0.001 || Math.abs(this.pendingDy) > 0.001) {
            this.yaw -= this.pendingDx * this.lookSensitivity;
            this.pitch -= this.pendingDy * this.lookSensitivity;
            this.pendingDx = 0;
            this.pendingDy = 0;

            // Clamp pitch to avoid gimbal flip
            this.pitch = Math.max(this.pitchRange[0], Math.min(this.pitchRange[1], this.pitch));
            this.entity.setEulerAngles(this.pitch, this.yaw, 0);
        }

        // 2. Read directional keyboard inputs
        const isForward = this.keys.has('KeyW') || this.keys.has('ArrowUp');
        const isBackward = this.keys.has('KeyS') || this.keys.has('ArrowDown');
        const isLeft = this.keys.has('KeyA') || this.keys.has('ArrowLeft');
        const isRight = this.keys.has('KeyD') || this.keys.has('ArrowRight');
        const isUp = this.keys.has('Space') || this.keys.has('KeyE');
        const isDown = this.keys.has('KeyC') || this.keys.has('KeyQ');

        // Determine walk vs sprint speed, dynamically evaluating current scene navigation config
        const baseSpeed = typeof this.navigation?.movementSpeed === 'number'
            ? this.navigation.movementSpeed
            : this.movementSpeed;
        const sprintSpeed = typeof this.navigation?.fastMovementSpeed === 'number'
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

        // 3. Smooth velocity acceleration and deceleration curves
        const accelRate = (inputLen > 0 || isUp || isDown) ? 8 : 12;
        const lerpFactor = Math.min(1, accelRate * clampedDt);
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
        window.removeEventListener('mousedown', this.onMouseDownBound);
        window.removeEventListener('mouseup', this.onMouseUpBound);
        window.removeEventListener('mousemove', this.onMouseMoveBound);
        document.removeEventListener('pointerlockchange', this.onPointerLockChangeBound);
    }
}
