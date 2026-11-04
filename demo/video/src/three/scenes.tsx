import { ThreeCanvas } from "@remotion/three";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { CameraRig, Car, JAY, MAYA, Person, Street, roundRect, useCanvasTexture } from "./parts";
import { LINE_AT, lineEnd } from "../timeline";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(0.33, 0, 0.2, 1);

const Sky: React.FC<{ tone?: "dusk" | "cabin" }> = ({ tone = "dusk" }) => (
  <AbsoluteFill style={{
    background: tone === "dusk"
      ? "linear-gradient(180deg, #121A36 0%, #2A2A5A 45%, #6B3F6E 78%, #C2665A 100%)"
      : "radial-gradient(ellipse at 50% 60%, #1E2433 0%, #0C0F17 75%)",
  }} />
);

// ---------------------------------------------------------------- scene 1 + relief: the parking lot

/** `t0` is the absolute second this scene instance starts at (to know who is speaking). */
export const StreetScene: React.FC<{ t0: number; variant: "intro" | "relief" }> = ({ t0, variant }) => {
  const frame = useCurrentFrame();
  const { width, height, fps, durationInFrames } = useVideoConfig();
  const t = t0 + frame / fps;
  const speaking = (id: string) => t >= LINE_AT[id] && t <= lineEnd(id);
  const jayTalk = variant === "intro" ? speaking("A01") || speaking("A03") || speaking("A04") : speaking("H01") || speaking("H03");
  const mayaTalk = variant === "intro" ? speaking("A02") || speaking("A05") : speaking("H02");
  // Comedy beat: after the submarine line, crickets, then a snap zoom on Maya's deadpan "Jay."
  const deadpan = variant === "intro" && t >= lineEnd("A04") + 0.05;
  let pos: [number, number, number];
  let look: [number, number, number];
  let fov = 38;
  if (deadpan) {
    const z = interpolate(t, [lineEnd("A04") + 0.05, lineEnd("A04") + 0.35], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
    pos = [interpolate(z, [0, 1], [2.0, 2.05]), 1.98, interpolate(z, [0, 1], [6.4, 3.55])];
    look = [2.3, 1.93, 1.25];
    fov = 30;
  } else if (variant === "intro") {
    const k = interpolate(frame, [0, Math.min(14 * fps, durationInFrames)], [0, 1], { ...clamp, easing: ease });
    pos = [interpolate(k, [0, 1], [5.5, 2.0]), interpolate(k, [0, 1], [3.3, 1.95]), interpolate(k, [0, 1], [12.5, 6.4])];
    look = [interpolate(k, [0, 1], [0.4, 1.4]), interpolate(k, [0, 1], [1.2, 1.45]), 0.3];
  } else {
    const k = interpolate(frame, [0, durationInFrames], [0, 1], { ...clamp, easing: ease });
    pos = [interpolate(k, [0, 1], [1.7, 1.55]), 1.95, interpolate(k, [0, 1], [5.4, 4.7])];
    look = [1.55, 1.6, 1.2];
  }
  return (
    <AbsoluteFill>
      <Sky />
      <ThreeCanvas width={width} height={height} camera={{ fov: 38, near: 0.1, far: 120 }}>
        <CameraRig pos={pos} look={look} fov={fov} />
        <fog attach="fog" args={["#2A2A5A", 18, 60]} />
        <hemisphereLight args={["#8FA4FF", "#2A1E2E", 0.55]} />
        <directionalLight position={[6, 9, 6]} intensity={0.9} color="#FFD7B0" />
        <directionalLight position={[-6, 4, -4]} intensity={0.35} color="#7FA2FF" />
        <Street frame={frame} />
        <directionalLight position={[2, 3, 8]} intensity={0.75} color="#FFE3C4" />
        <Car position={[-0.2, 0, -1.9]} rotationY={0.12} />
        <Person look={JAY} frame={frame} position={[0.85, 0, 1.2]} rotationY={variant === "intro" ? 0.45 : 0.25}
          talking={jayTalk} phone={variant === "intro"} lookAtPhone={variant === "intro" && !jayTalk}
          mood={variant === "relief" && !speaking("H03") ? "happy" : "neutral"} />
        <Person look={MAYA} frame={frame + 40} position={[2.35, 0, 1.25]} rotationY={deadpan ? 0.05 : variant === "intro" ? -0.45 : -0.6}
          talking={mayaTalk} mood={variant === "intro" && t > LINE_AT.A03 ? "worried" : variant === "relief" && speaking("H03") ? "worried" : "neutral"} />
      </ThreeCanvas>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- dashboard (tape trick / honest bulb check)

const LIGHTS = [
  { label: "CHECK\nENGINE", color: "#FFB020" },
  { label: "ABS", color: "#FFB020" },
  { label: "AIRBAG", color: "#FF3B3B" },
  { label: "OIL", color: "#FF3B3B" },
  { label: "BATTERY", color: "#FF3B3B" },
  { label: "BRAKE", color: "#FF3B3B" },
];

const Icon: React.FC<{ i: number; on: boolean; x: number }> = ({ i, on, x }) => {
  const { label, color } = LIGHTS[i];
  const tex = useCanvasTexture(256, 160, (c) => {
    c.fillStyle = "#07090D";
    c.fillRect(0, 0, 256, 160);
    c.strokeStyle = color;
    c.lineWidth = 8;
    roundRect(c, 14, 14, 228, 132, 22);
    c.stroke();
    c.fillStyle = color;
    c.textAlign = "center";
    const rows = label.split("\n");
    c.font = `800 ${rows.length > 1 ? 44 : 52}px Inter`;
    rows.forEach((r, k) => c.fillText(r, 128, rows.length > 1 ? 70 + k * 48 : 98));
  }, [i]);
  return (
    <mesh position={[x, 0, 0.01]}>
      <planeGeometry args={[0.46, 0.29]} />
      <meshBasicMaterial map={tex} toneMapped={false} transparent opacity={on ? 1 : 0.13} />
    </mesh>
  );
};

const Gauge: React.FC<{ x: number; label: string; max: number; value: number }> = ({ x, label, max, value }) => {
  const tex = useCanvasTexture(512, 512, (c) => {
    const g = c.createRadialGradient(256, 256, 40, 256, 256, 250);
    g.addColorStop(0, "#151A24");
    g.addColorStop(1, "#05070B");
    c.fillStyle = g;
    c.beginPath(); c.arc(256, 256, 250, 0, Math.PI * 2); c.fill();
    c.strokeStyle = "#9FB6D9"; c.lineWidth = 6;
    c.beginPath(); c.arc(256, 256, 236, 0, Math.PI * 2); c.stroke();
    for (let k = 0; k <= 10; k++) {
      const a = Math.PI * 0.75 + (k / 10) * Math.PI * 1.5;
      c.strokeStyle = "#DCE6F5"; c.lineWidth = k % 2 ? 4 : 8;
      c.beginPath(); c.moveTo(256 + Math.cos(a) * 200, 256 + Math.sin(a) * 200); c.lineTo(256 + Math.cos(a) * 228, 256 + Math.sin(a) * 228); c.stroke();
      if (k % 2 === 0) {
        c.fillStyle = "#DCE6F5"; c.font = "600 34px Inter"; c.textAlign = "center"; c.textBaseline = "middle";
        c.fillText(String(Math.round((k / 10) * max)), 256 + Math.cos(a) * 160, 256 + Math.sin(a) * 160);
      }
    }
    c.fillStyle = "#8FA3C0"; c.font = "600 30px Inter"; c.textAlign = "center"; c.fillText(label, 256, 370);
  }, [label, max]);
  const angle = Math.PI * 0.75 + value * Math.PI * 1.5; // canvas angle, clockwise from +x
  return (
    <group position={[x, 0, 0]}>
      <mesh><circleGeometry args={[0.62, 48]} /><meshBasicMaterial map={tex} toneMapped={false} /></mesh>
      <mesh position={[0, 0, 0.02]} rotation={[0, 0, -angle]}>
        <mesh position={[0.24, 0, 0]}><boxGeometry args={[0.5, 0.025, 0.01]} /><meshBasicMaterial color="#FF5A3C" toneMapped={false} /></mesh>
      </mesh>
      <mesh position={[0, 0, 0.03]}><circleGeometry args={[0.05, 20]} /><meshBasicMaterial color="#2A2F3A" /></mesh>
    </group>
  );
};

/** variant "tape": lights on, check-engine dark under tape. variant "sweep": lights come on one by one, all on. */
export const DashboardScene: React.FC<{ variant: "tape" | "sweep" }> = ({ variant }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const tapeTex = useCanvasTexture(620, 260, (c) => {
    c.fillStyle = "#DCCDA6"; c.fillRect(0, 0, 620, 260);
    c.fillStyle = "rgba(0,0,0,.06)"; for (let x = 0; x < 620; x += 14) c.fillRect(x, 0, 6, 260);
    c.fillStyle = "#26334D"; c.font = "700 54px 'Comic Neue', 'Segoe Print', cursive"; c.textAlign = "center";
    c.save(); c.translate(310, 150); c.rotate(-0.04); c.fillText("nothing to see here :)", 0, 0); c.restore();
  }, []);
  const tapeIn = interpolate(frame, [1.0 * fps, 1.25 * fps], [1, 0], { ...clamp, easing: Easing.out(Easing.back(1.4)) });
  const k = interpolate(frame, [0, 6 * fps], [0, 1], { ...clamp, easing: ease });
  const pos: [number, number, number] = variant === "tape"
    ? [interpolate(k, [0, 1], [-0.6, -0.25]), interpolate(k, [0, 1], [0.35, 0.15]), interpolate(k, [0, 1], [3.6, 2.4])]
    : [interpolate(k, [0, 1], [-0.2, -0.7]), 0.25, interpolate(k, [0, 1], [4.2, 3.6])];
  const look: [number, number, number] = variant === "tape" ? [-0.55, -0.05, 0] : [-1.2, 0, 0];
  const lightOn = (i: number) => (variant === "tape" ? true : frame > 0.5 * fps + i * 4);
  const needle = variant === "sweep" ? interpolate(frame, [0.4 * fps, 1.2 * fps, 2 * fps], [0, 1, 0], clamp) : 0;
  return (
    <AbsoluteFill>
      <Sky tone="cabin" />
      <ThreeCanvas width={width} height={height} camera={{ fov: 34, near: 0.05, far: 50 }}>
        <CameraRig pos={pos} look={look} />
        <ambientLight intensity={0.25} />
        <pointLight position={[0, 1.4, 2.2]} intensity={6} distance={8} color="#B8C8FF" />
        {/* cluster housing */}
        <mesh position={[0, 0, -0.08]}><boxGeometry args={[4.2, 1.9, 0.12]} /><meshStandardMaterial color="#0E1118" roughness={0.6} /></mesh>
        <mesh position={[0, 1.02, 0.2]} rotation={[-0.5, 0, 0]}><boxGeometry args={[4.4, 0.12, 0.8]} /><meshStandardMaterial color="#1A1F2B" roughness={0.8} /></mesh>
        <Gauge x={-1.15} label="km/h" max={240} value={needle} />
        <Gauge x={1.15} label="rpm x1000" max={8} value={needle * 0.85} />
        {/* warning lights row */}
        <group position={[0, -0.05, 0]}>
          {LIGHTS.map((_, i) => (
            <group key={i} position={[(i % 2 === 0 ? -0.26 : 0.26), 0.36 - Math.floor(i / 2) * 0.34, 0]}>
              <Icon i={i} on={lightOn(i)} x={0} />
            </group>
          ))}
        </group>
        {variant === "tape" && (
          <mesh position={[-0.26 - tapeIn * 1.2, 0.31 + tapeIn * 0.8, 0.03]} rotation={[0, 0, -0.12 + tapeIn * 0.6]}>
            <planeGeometry args={[0.62, 0.26]} />
            <meshStandardMaterial map={tapeTex} roughness={0.9} />
          </mesh>
        )}
        {/* steering wheel rim, out of focus in front */}
        <mesh position={[0, -1.55, 0.9]} rotation={[0.35, 0, 0]}><torusGeometry args={[1.25, 0.08, 16, 64]} /><meshStandardMaterial color="#111318" roughness={0.6} /></mesh>
      </ThreeCanvas>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- windshield: code card next to the VIN plate

export const VinScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const plate = useCanvasTexture(1024, 160, (c) => {
    c.fillStyle = "#C9CED6"; c.fillRect(0, 0, 1024, 160);
    c.fillStyle = "#2A2F38"; c.font = "700 92px DejaVu Sans Mono"; c.textAlign = "center"; c.textBaseline = "middle";
    c.fillText("1HGCM82633A004352", 512, 84);
  }, []);
  const card = useCanvasTexture(640, 400, (c) => {
    c.fillStyle = "#FBFBF7"; c.fillRect(0, 0, 640, 400);
    c.fillStyle = "#9AA0A6"; c.font = "600 40px Inter"; c.fillText("Code", 40, 70);
    c.fillStyle = "#1F2BA6"; c.font = "800 138px Inter"; c.textAlign = "center"; c.fillText("K7Q2XM", 320, 262);
  }, []);
  const slide = interpolate(frame, [0.5 * fps, 1.3 * fps], [1, 0], { ...clamp, easing: Easing.out(Easing.cubic) });
  const k = interpolate(frame, [0, 4.8 * fps], [0, 1], { ...clamp, easing: ease });
  return (
    <AbsoluteFill>
      <Sky tone="cabin" />
      <ThreeCanvas width={width} height={height} camera={{ fov: 36, near: 0.05, far: 60 }}>
        <CameraRig pos={[interpolate(k, [0, 1], [0.6, 0.25]), 1.0, interpolate(k, [0, 1], [3.1, 2.5])]} look={[0.05, 0.2, 0]} />
        <ambientLight intensity={0.5} />
        <directionalLight position={[2, 4, 3]} intensity={1.1} color="#FFE7C7" />
        {/* dashboard top + windshield */}
        <mesh rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[8, 3]} /><meshStandardMaterial color="#1B1F28" roughness={0.9} /></mesh>
        <mesh position={[0, 0.9, -1.45]} rotation={[-0.95, 0, 0]}><planeGeometry args={[8, 2.6]} /><meshStandardMaterial color="#6E8BB8" transparent opacity={0.22} metalness={0.9} roughness={0.05} /></mesh>
        {/* VIN plate */}
        <mesh position={[-0.95, 0.02, -0.25]} rotation={[-Math.PI / 2.4, 0, 0]}><planeGeometry args={[1.5, 0.24]} /><meshStandardMaterial map={plate} metalness={0.4} roughness={0.5} /></mesh>
        {/* the paper card, sliding in, held up next to the plate */}
        <group position={[0.22 + slide * 2.4, 0.42, -0.05]} rotation={[-0.25, -0.15, 0.04 + slide * 0.3]}>
          <mesh><planeGeometry args={[0.96, 0.6]} /><meshBasicMaterial map={card} toneMapped={false} /></mesh>
        </group>
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
