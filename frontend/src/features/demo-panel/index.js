// 데모 스위치 (D). 화면에는 DemoPanel 을 한 번 붙이고, API 클라이언트는 withDemo 로 요청 본문에 demo 를 넣는다.
export { default as DemoPanel } from "./DemoPanel.jsx";
export { useDemoSwitch } from "./useDemoSwitch.js";
export { getDemoOverride, withDemo, SCENES, WEATHER_PRESETS } from "./demoStore.js";
