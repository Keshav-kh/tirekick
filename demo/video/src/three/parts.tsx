// Low-poly 3D building blocks. Everything animates from props driven by useCurrentFrame() upstream.
import { useMemo } from "react";
import * as THREE from "three";
import { useThree } from "@react-three/fiber";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

/** Box with softened edges: low-poly charm, without razor-sharp corners. */
export const RBox: React.FC<{ args: [number, number, number]; radius?: number; position?: [number, number, number]; rotation?: [number, number, number]; children?: React.ReactNode }> = ({
  args, radius = 0.06, position, rotation, children,
}) => {
  const geo = useMemo(() => new RoundedBoxGeometry(args[0], args[1], args[2], 4, Math.min(radius, Math.min(...args) / 2 - 0.001)), [args[0], args[1], args[2], radius]);
  return <mesh geometry={geo} position={position} rotation={rotation}>{children}</mesh>;
};

// ---------------------------------------------------------------- canvas textures (deterministic)

export function useCanvasTexture(w: number, h: number, draw: (c: CanvasRenderingContext2D) => void, deps: unknown[]) {
  return useMemo(() => {
    const cv = document.createElement("canvas");
    cv.width = w;
    cv.height = h;
    draw(cv.getContext("2d")!);
    const tex = new THREE.CanvasTexture(cv);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 4;
    return tex;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export const roundRect = (c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) => {
  c.beginPath();
  c.moveTo(x + r, y);
  c.arcTo(x + w, y, x + w, y + h, r);
  c.arcTo(x + w, y + h, x, y + h, r);
  c.arcTo(x, y + h, x, y, r);
  c.arcTo(x, y, x + w, y, r);
  c.closePath();
};

// ---------------------------------------------------------------- camera

export const CameraRig: React.FC<{ pos: [number, number, number]; look: [number, number, number]; fov?: number }> = ({ pos, look, fov }) => {
  const { camera } = useThree();
  camera.position.set(...pos);
  camera.lookAt(...look);
  if (fov && (camera as THREE.PerspectiveCamera).fov !== fov) {
    (camera as THREE.PerspectiveCamera).fov = fov;
    (camera as THREE.PerspectiveCamera).updateProjectionMatrix();
  }
  return null;
};

// ---------------------------------------------------------------- shadows (cheap blob shadows)

export const Blob: React.FC<{ position: [number, number, number]; scale: [number, number]; opacity?: number }> = ({ position, scale, opacity = 0.45 }) => {
  const tex = useCanvasTexture(128, 128, (c) => {
    const g = c.createRadialGradient(64, 64, 4, 64, 64, 64);
    g.addColorStop(0, "rgba(0,0,0,1)");
    g.addColorStop(1, "rgba(0,0,0,0)");
    c.fillStyle = g;
    c.fillRect(0, 0, 128, 128);
  }, []);
  return (
    <mesh position={position} rotation={[-Math.PI / 2, 0, 0]} scale={[scale[0], scale[1], 1]}>
      <planeGeometry args={[1, 1]} />
      <meshBasicMaterial map={tex} transparent opacity={opacity} depthWrite={false} />
    </mesh>
  );
};

// ---------------------------------------------------------------- car

export const Car: React.FC<{ position?: [number, number, number]; rotationY?: number; color?: string; sign?: boolean }> = ({
  position = [0, 0, 0], rotationY = 0, color = "#AFC0D3", sign = true,
}) => {
  const signTex = useCanvasTexture(512, 300, (c) => {
    c.fillStyle = "#FFD23F";
    roundRect(c, 0, 0, 512, 300, 24);
    c.fill();
    c.fillStyle = "#1A1A1A";
    c.font = "800 92px Inter";
    c.textAlign = "center";
    c.fillText("FOR SALE", 256, 120);
    c.font = "800 118px Inter";
    c.fillText("$4,800", 256, 250);
  }, []);
  const body = <meshStandardMaterial color={color} metalness={0.55} roughness={0.32} />;
  const glass = <meshStandardMaterial color="#1B2333" metalness={0.8} roughness={0.15} />;
  const tire = <meshStandardMaterial color="#15171C" roughness={0.9} />;
  return (
    <group position={position} rotation={[0, rotationY, 0]}>
      <Blob position={[0, 0.01, 0]} scale={[5.2, 2.6]} opacity={0.55} />
      {/* lower body */}
      <RBox position={[0, 0.62, 0]} args={[4.3, 0.62, 1.82]} radius={0.2}>{body}</RBox>
      {/* hood and trunk slopes */}
      <RBox position={[1.5, 0.95, 0]} rotation={[0, 0, -0.12]} args={[1.3, 0.16, 1.76]} radius={0.07}>{body}</RBox>
      <RBox position={[-1.68, 0.95, 0]} rotation={[0, 0, 0.08]} args={[0.95, 0.16, 1.76]} radius={0.07}>{body}</RBox>
      {/* cabin */}
      <RBox position={[-0.15, 1.3, 0]} args={[2.1, 0.62, 1.6]} radius={0.16}>{glass}</RBox>
      <RBox position={[-0.15, 1.62, 0]} args={[1.85, 0.08, 1.58]} radius={0.035}>{body}</RBox>
      {/* pillars */}
      {[-1.15, 0.85].map((x) => (
        <RBox key={x} position={[x, 1.3, 0]} rotation={[0, 0, x > 0 ? 0.55 : -0.45]} args={[0.09, 0.72, 1.62]} radius={0.04}>{body}</RBox>
      ))}
      {/* wheels */}
      {[[1.35, 0.86], [1.35, -0.86], [-1.35, 0.86], [-1.35, -0.86]].map(([x, z]) => (
        <group key={`${x}${z}`} position={[x, 0.38, z]} rotation={[Math.PI / 2, 0, 0]}>
          <mesh><cylinderGeometry args={[0.33, 0.33, 0.26, 40]} />{tire}</mesh>
          <mesh rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[0.31, 0.1, 16, 48]} />{tire}</mesh>
          <mesh position={[0, z > 0 ? 0.15 : -0.15, 0]}><cylinderGeometry args={[0.2, 0.2, 0.02, 40]} /><meshStandardMaterial color="#C9D2DC" metalness={0.9} roughness={0.3} /></mesh>
        </group>
      ))}
      {/* lights */}
      {[0.6, -0.6].map((z) => (
        <mesh key={`h${z}`} position={[2.16, 0.78, z]}><boxGeometry args={[0.04, 0.14, 0.42]} /><meshStandardMaterial color="#FFF6D8" emissive="#FFF2C2" emissiveIntensity={1.4} /></mesh>
      ))}
      {[0.62, -0.62].map((z) => (
        <mesh key={`t${z}`} position={[-2.16, 0.8, z]}><boxGeometry args={[0.04, 0.14, 0.38]} /><meshStandardMaterial color="#B3132B" emissive="#E0213F" emissiveIntensity={0.9} /></mesh>
      ))}
      {/* FOR SALE sign in the rear side window */}
      {sign && (
        <mesh position={[-0.55, 1.3, 0.815]}>
          <planeGeometry args={[0.85, 0.5]} />
          <meshBasicMaterial map={signTex} toneMapped={false} />
        </mesh>
      )}
    </group>
  );
};

// ---------------------------------------------------------------- people

export type PersonLook = { shirt: string; pants: string; skin: string; hair: string; female?: boolean };

export const Person: React.FC<{
  look: PersonLook; position: [number, number, number]; rotationY?: number; frame: number;
  talking?: boolean; phone?: boolean; mood?: "neutral" | "worried" | "happy"; lookAtPhone?: boolean;
}> = ({ look, position, rotationY = 0, frame, talking = false, phone = false, mood = "neutral", lookAtPhone = false }) => {
  const skin = <meshStandardMaterial color={look.skin} roughness={0.7} />;
  const shirt = <meshStandardMaterial color={look.shirt} roughness={0.8} />;
  const pants = <meshStandardMaterial color={look.pants} roughness={0.85} />;
  const hair = <meshStandardMaterial color={look.hair} roughness={0.9} />;
  const breathe = Math.sin(frame / 22) * 0.012;
  const mouthOpen = talking ? 0.35 + 0.65 * Math.abs(Math.sin(frame * 0.85)) * (0.55 + 0.45 * Math.sin(frame * 0.31)) : 0;
  const blink = frame % 97 < 4 ? 0.15 : 1;
  const nod = talking ? Math.sin(frame * 0.18) * 0.06 : lookAtPhone ? 0.28 : 0;
  const tilt = talking ? Math.sin(frame * 0.07) * 0.05 : 0;
  const brow = mood === "worried" ? 0.25 : mood === "happy" ? -0.1 : 0;
  const armSwing = talking && !phone ? Math.sin(frame * 0.2) * 0.25 : 0;
  return (
    <group position={position} rotation={[0, rotationY, 0]}>
      <Blob position={[0, 0.01, 0]} scale={[1.1, 0.8]} />
      {/* legs */}
      {[-0.13, 0.13].map((x) => (
        <mesh key={x} position={[x, 0.45, 0]}><capsuleGeometry args={[0.11, 0.62, 12, 24]} />{pants}</mesh>
      ))}
      {[-0.13, 0.13].map((x) => (
        <RBox key={`s${x}`} position={[x, 0.07, 0.05]} args={[0.2, 0.13, 0.34]} radius={0.055}><meshStandardMaterial color="#F2F2F2" /></RBox>
      ))}
      {/* torso */}
      <group position={[0, 1.18 + breathe, 0]}>
        <mesh scale={[1, 1, 0.75]}><capsuleGeometry args={[0.27, 0.5, 16, 32]} />{shirt}</mesh>
        {look.female ? null : <mesh position={[0, 0.25, -0.17]} scale={[1, 0.6, 0.6]}><sphereGeometry args={[0.26, 32, 20]} />{shirt}</mesh>}
      </group>
      {/* arms */}
      <group position={[-0.36, 1.42 + breathe, 0]} rotation={[armSwing, 0, 0.12]}>
        <mesh position={[0, -0.32, 0]}><capsuleGeometry args={[0.085, 0.5, 12, 20]} />{shirt}</mesh>
        <mesh position={[0, -0.66, 0]}><sphereGeometry args={[0.085, 24, 16]} />{skin}</mesh>
      </group>
      <group position={[0.36, 1.42 + breathe, 0]} rotation={phone ? [-1.15, 0.35, -0.2] : [-armSwing, 0, -0.12]}>
        <mesh position={[0, -0.32, 0]}><capsuleGeometry args={[0.085, 0.5, 12, 20]} />{shirt}</mesh>
        <mesh position={[0, -0.66, 0]}><sphereGeometry args={[0.085, 24, 16]} />{skin}</mesh>
        {phone && (
          <group position={[0, -0.72, 0.05]} rotation={[1.2, 0, 0]}>
            <RBox args={[0.16, 0.3, 0.022]} radius={0.01}><meshStandardMaterial color="#202124" metalness={0.6} roughness={0.3} /></RBox>
            <mesh position={[0, 0, 0.012]}><planeGeometry args={[0.14, 0.27]} /><meshStandardMaterial color="#DDF6EF" emissive="#9FE8D2" emissiveIntensity={0.9} /></mesh>
          </group>
        )}
      </group>
      {/* neck + head */}
      <mesh position={[0, 1.66 + breathe, 0]}><cylinderGeometry args={[0.07, 0.08, 0.14, 24]} />{skin}</mesh>
      <group position={[0, 1.95 + breathe, 0]} rotation={[nod, 0, tilt]}>
        <mesh><sphereGeometry args={[0.3, 48, 32]} />{skin}</mesh>
        {/* hair */}
        <mesh position={[0, 0.09, -0.03]} scale={[1.04, look.female ? 0.95 : 0.78, 1.04]}>
          <sphereGeometry args={[0.3, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2]} />{hair}
        </mesh>
        {look.female && <mesh position={[0, 0.28, -0.2]}><sphereGeometry args={[0.13, 32, 20]} />{hair}</mesh>}
        {look.female && <mesh position={[0, -0.05, -0.12]} scale={[1.05, 1.1, 0.9]}><sphereGeometry args={[0.3, 48, 24, 0, Math.PI * 2, Math.PI / 2.4, Math.PI / 2.2]} />{hair}</mesh>}
        {/* eyes */}
        {[-0.1, 0.1].map((x) => (
          <group key={x} position={[x, 0.03, 0.265]}>
            <mesh scale={[1, blink, 1]}><sphereGeometry args={[0.042, 24, 16]} /><meshStandardMaterial color="#FFFFFF" /></mesh>
            <mesh position={[0, 0, 0.03]} scale={[1, blink, 1]}><sphereGeometry args={[0.024, 20, 12]} /><meshStandardMaterial color="#1B1B1F" /></mesh>
            <mesh position={[0, 0.075 + brow * 0.04, 0.02]} rotation={[0, 0, (x > 0 ? -1 : 1) * brow]}><boxGeometry args={[0.08, 0.015, 0.01]} />{hair}</mesh>
          </group>
        ))}
        {/* mouth */}
        <mesh position={[0, -0.12, 0.27]} scale={[mood === "happy" ? 1.5 : 1, (mood === "happy" ? 0.4 : 0.25) + mouthOpen * 0.9, 0.5]}>
          <sphereGeometry args={[0.05, 24, 16]} /><meshStandardMaterial color="#5A2430" />
        </mesh>
      </group>
    </group>
  );
};

export const JAY: PersonLook = { shirt: "#2F6BEF", pants: "#2B2F3A", skin: "#C88E64", hair: "#1E1712" };
export const MAYA: PersonLook = { shirt: "#E89A2E", pants: "#33465E", skin: "#8D5A3B", hair: "#16100C", female: true };

// ---------------------------------------------------------------- street set

export const Street: React.FC<{ frame: number }> = ({ frame }) => {
  const windows = useMemo(() => {
    const out: { p: [number, number, number]; on: boolean }[] = [];
    let seed = 11;
    const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
    for (const [bx, bw, bh, bz] of [[-14, 6, 9, -16], [-6, 7, 13, -20], [3, 6, 8, -15], [11, 8, 11, -18], [19, 6, 7, -14]] as const) {
      for (let y = 1.5; y < bh - 1; y += 1.6) for (let x = bx - bw / 2 + 0.8; x < bx + bw / 2 - 0.6; x += 1.3) {
        out.push({ p: [x, y, bz + 3.01], on: rnd() > 0.45 });
      }
    }
    return out;
  }, []);
  return (
    <group>
      {/* asphalt + sidewalk + lot lines */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}><planeGeometry args={[80, 60]} /><meshStandardMaterial color="#2C313D" roughness={0.95} /></mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, -6.5]}><planeGeometry args={[80, 5]} /><meshStandardMaterial color="#4A505E" roughness={0.9} /></mesh>
      {[-6, -1, 4, 9].map((x) => (
        <mesh key={x} rotation={[-Math.PI / 2, 0, 0]} position={[x, 0.015, -1.6]}><planeGeometry args={[0.12, 4.5]} /><meshStandardMaterial color="#D8DCE3" /></mesh>
      ))}
      {/* buildings with lit windows */}
      {[[-14, 6, 9, -16, "#232A45"], [-6, 7, 13, -20, "#1E2440"], [3, 6, 8, -15, "#262D4B"], [11, 8, 11, -18, "#20263F"], [19, 6, 7, -14, "#272E4C"]].map(([x, w, h, z, c]) => (
        <RBox key={`${x}`} position={[x as number, (h as number) / 2, z as number]} args={[w as number, h as number, 6]} radius={0.25}><meshStandardMaterial color={c as string} roughness={1} /></RBox>
      ))}
      {windows.map((wdw, i) => (
        <mesh key={i} position={wdw.p}><planeGeometry args={[0.7, 0.9]} /><meshStandardMaterial color={wdw.on ? "#FFD58A" : "#2E3658"} emissive={wdw.on ? "#FFC266" : "#000000"} emissiveIntensity={wdw.on ? 0.8 + 0.2 * Math.sin(i + frame / 40) * (i % 7 === 0 ? 1 : 0) : 0} /></mesh>
      ))}
      {/* street lamps */}
      {[-7, 7].map((x) => (
        <group key={x} position={[x, 0, -4.6]}>
          <mesh position={[0, 2.4, 0]}><cylinderGeometry args={[0.06, 0.09, 4.8, 24]} /><meshStandardMaterial color="#3A3F4B" /></mesh>
          <mesh position={[0.45, 4.75, 0]} rotation={[0, 0, Math.PI / 2]}><cylinderGeometry args={[0.04, 0.04, 0.9, 20]} /><meshStandardMaterial color="#3A3F4B" /></mesh>
          <mesh position={[0.85, 4.65, 0]}><sphereGeometry args={[0.16, 32, 20]} /><meshStandardMaterial color="#FFE6B0" emissive="#FFC266" emissiveIntensity={2.2} /></mesh>
          <pointLight position={[0.85, 4.4, 0.4]} color="#FFC77A" intensity={14} distance={14} decay={1.6} />
        </group>
      ))}
    </group>
  );
};
