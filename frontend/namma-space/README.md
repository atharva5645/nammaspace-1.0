# NammaSpace Web Viewer (`namma-space`)

> **High-performance 3D Gaussian Splatting (3DGS) web viewer powered by React 19, TypeScript, Vite, and PlayCanvas React.**

Part of the [NammaSpace](../README.md) spatial computing ecosystem.

---

## 🌟 Overview

`namma-space` is the client-facing interactive web application of the NammaSpace project. It renders real-time 3D Gaussian Splats (`.sog` and `.ply`) directly in the browser with high framerates, orbit camera controls, and an integrated real-time PlayCanvas Inspector.

### Features
- **Modern React 19 Architecture**: Declarative 3D entity hierarchy via `@playcanvas/react`.
- **Fast Vite Toolchain**: Instant hot-module replacement (HMR) and optimized static asset bundling.
- **Optimized Rendering**: Fragment-bound splat rendering with antialiasing tuning for smooth 60+ FPS performance on mobile and desktop devices.
- **First-Person & Rail Navigation**: Walk down retail aisles with smooth WASD/Space/C controls and runtime speed adjustment (`[` / `]`).
- **Embedded Inspector**: On-the-fly debugging of the scene graph, shaders, textures, and assets via `@playcanvas/inspector`.

---

## 🚀 Getting Started

### Prerequisites
- Node.js 22.x or later
- npm 10.x or later

### Installation & Development

```bash
# Install dependencies
npm install

# Start Vite development server
npm run dev
```

Visit [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🎮 Controls & Inspector

- **Mouse / Touch**: Click and drag to orbit around the 3D Gaussian splat. Scroll to zoom.
- **Toggle Inspector**: Press <kbd>`</kbd> (backquote) to open the PlayCanvas Inspector panel. Inspect entities, draw calls, materials, and scene performance metrics.
- **Pause Simulation**: Press <kbd>F9</kbd> to freeze rendering.
- **Step Frame**: Press <kbd>F10</kbd> to advance rendering by a single frame.

> *Note: The Inspector is automatically excluded from production builds.*

---

## 📁 Loading Your Own Splats

By default, the viewer loads a sample splat asset. To render your own capture:

1. Process your capture using the [Capture Pipeline](../pipeline-capture-splat) or download a `.ply` / `.sog` file (e.g. from [SuperSplat](https://superspl.at)).
2. Place the file inside the `public/` directory (e.g., `public/my-scene.sog`).
3. In [`src/App.tsx`](src/App.tsx), update `SPLAT_URL`:
   ```tsx
   const SPLAT_URL = '/my-scene.sog';
   ```
4. Adjust entity rotation and scale if necessary to orient your capture upright:
   ```tsx
   <Entity name="my splat" position={[0, 0, 0]} rotation={[0, 0, 180]}>
       <GSplat asset={asset} />
   </Entity>
   ```

---

## 🛠️ Available Scripts

| Command | Description |
| :--- | :--- |
| `npm run dev` | Starts Vite dev server with Hot Module Replacement and Inspector |
| `npm run build` | Builds optimized production bundle into `dist/` |
| `npm run start` | Previews the production build locally |
| `npm run typecheck` | Executes TypeScript type validation (`tsc --noEmit`) |
| `npm run lint` | Runs ESLint |
| `npm run lint:fix` | Runs ESLint and automatically applies fixes |
| `npm run fmt` | Checks code formatting with Prettier |
| `npm run fmt:fix` | Formats code with Prettier |

---

## 🔗 Related Components

- [NammaSpace Root Documentation](../README.md)
- [Capture & Training Pipeline (`pipeline-capture-splat`)](../pipeline-capture-splat)
- [Splat Transformation & Compression CLI (`tool-splat-transform`)](../tool-splat-transform)
- [3DGS Research Library (`research-awesome-3dgs`)](../research-awesome-3dgs)
