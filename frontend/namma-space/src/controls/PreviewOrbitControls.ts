import { Script, Vec3 } from 'playcanvas';

/** Lightweight pointer-driven orbit controls for the interactive wireframe preview. */
export class PreviewOrbitControls extends Script {
    static scriptName = 'previewOrbitControls';

    public pivot: [number, number, number] = [0, 1.2, 0];
    public orbitSensitivity = 0.006;
    public zoomSensitivity = 0.0015;
    public minDistance = 3.5;
    public maxDistance = 11;

    private canvas?: HTMLCanvasElement;
    private dragging = false;
    private pointerId: number | null = null;
    private yaw = 0;
    private pitch = 0.42;
    private distance = 7.5;

    private onPointerDownBound = this.onPointerDown.bind(this);
    private onPointerMoveBound = this.onPointerMove.bind(this);
    private onPointerUpBound = this.onPointerUp.bind(this);
    private onWheelBound = this.onWheel.bind(this);

    initialize() {
        this.canvas = this.app.graphicsDevice.canvas;
        const current = this.entity.getPosition();
        const dx = current.x - this.pivot[0];
        const dy = current.y - this.pivot[1];
        const dz = current.z - this.pivot[2];
        this.distance = Math.max(this.minDistance, Math.hypot(dx, dy, dz));
        this.yaw = Math.atan2(dx, dz);
        this.pitch = Math.asin(Math.min(0.95, Math.max(-0.95, dy / this.distance)));
        this.canvas.addEventListener('pointerdown', this.onPointerDownBound);
        this.canvas.addEventListener('pointermove', this.onPointerMoveBound);
        this.canvas.addEventListener('pointerup', this.onPointerUpBound);
        this.canvas.addEventListener('pointercancel', this.onPointerUpBound);
        this.canvas.addEventListener('wheel', this.onWheelBound, { passive: false });
        this.updateCamera();
    }

    private onPointerDown(event: PointerEvent) {
        if (event.button !== 0) return;
        this.dragging = true;
        this.pointerId = event.pointerId;
        this.canvas?.setPointerCapture(event.pointerId);
    }

    private onPointerMove(event: PointerEvent) {
        if (!this.dragging || event.pointerId !== this.pointerId) return;
        this.yaw -= event.movementX * this.orbitSensitivity;
        this.pitch = Math.max(0.08, Math.min(1.25, this.pitch + event.movementY * this.orbitSensitivity));
        this.updateCamera();
    }

    private onPointerUp(event: PointerEvent) {
        if (this.pointerId !== null && event.pointerId !== this.pointerId) return;
        this.dragging = false;
        this.pointerId = null;
    }

    private onWheel(event: WheelEvent) {
        event.preventDefault();
        this.distance = Math.max(this.minDistance, Math.min(this.maxDistance, this.distance + event.deltaY * this.zoomSensitivity));
        this.updateCamera();
    }

    private updateCamera() {
        const horizontal = this.distance * Math.cos(this.pitch);
        const position = new Vec3(
            this.pivot[0] + horizontal * Math.sin(this.yaw),
            this.pivot[1] + this.distance * Math.sin(this.pitch),
            this.pivot[2] + horizontal * Math.cos(this.yaw)
        );
        this.entity.setPosition(position);
        this.entity.lookAt(new Vec3(...this.pivot));
    }

    destroy() {
        this.canvas?.removeEventListener('pointerdown', this.onPointerDownBound);
        this.canvas?.removeEventListener('pointermove', this.onPointerMoveBound);
        this.canvas?.removeEventListener('pointerup', this.onPointerUpBound);
        this.canvas?.removeEventListener('pointercancel', this.onPointerUpBound);
        this.canvas?.removeEventListener('wheel', this.onWheelBound);
    }
}
