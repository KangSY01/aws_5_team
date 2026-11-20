import TravelPreview from "./components/TravelPreview.jsx";
import { DemoPanel, useDemoSwitch } from "./features/demo-panel";

export default function App() {
  const { enabled } = useDemoSwitch();
  return <><TravelPreview key={enabled ? "demo" : "normal"} demoMode={enabled} /><DemoPanel /></>;
}
