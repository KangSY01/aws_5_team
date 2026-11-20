import { useState } from "react";
import TravelPreview, { getSavedLanguage } from "./components/TravelPreview.jsx";
import TravelerProfileForm, { travelerCopy, travelerProfileKey } from "./components/TravelerProfile.jsx";
import { DemoPanel, useDemoSwitch } from "./features/demo-panel";

export default function App() {
  const { enabled } = useDemoSwitch();
  const [traveler, setTraveler] = useState(() => {
    try {
      return JSON.parse(window.localStorage.getItem(travelerProfileKey));
    } catch {
      return null;
    }
  });
  function saveTraveler(profile) {
    setTraveler(profile);
    try {
      window.localStorage.setItem(travelerProfileKey, JSON.stringify(profile));
    } catch {
      // The profile is still available for this session.
    }
  }
  if (!traveler) {
    const language = getSavedLanguage();
    function start(profile) {
      if (window.location.hash === "#profile") {
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
      }
      saveTraveler(profile);
    }
    return <main className="traveler-onboarding" lang={language}>
      <section aria-labelledby="traveler-profile-heading">
        <h1 id="traveler-profile-heading">{travelerCopy(language).title}</h1>
        <TravelerProfileForm language={language} firstVisit onSave={start} onCancel={() => start({})} />
      </section>
    </main>;
  }
  return <><TravelPreview key={enabled ? "demo" : "normal"} demoMode={enabled} traveler={traveler}
    onTravelerSave={saveTraveler} /><DemoPanel /></>;
}
