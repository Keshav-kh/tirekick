import { Composition } from "remotion";
import { Story } from "./Story";
import { FPS, TOTAL_S } from "./timeline";

export const MyComposition = () => (
  <Composition id="TireKickStory" component={Story} durationInFrames={Math.ceil(TOTAL_S * FPS)} fps={FPS} width={1920} height={1080} />
);
