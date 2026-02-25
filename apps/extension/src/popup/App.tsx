export const App = () => {
  const openSettings = () => {
    chrome.runtime.openOptionsPage();
  };

  return (
    <main className="popup-shell">
      <h1>Wealthsimple Prospector</h1>
      <p>
        Go to any LinkedIn profile page to open the sidebar and start scoring prospects and
        generating draft outreach.
      </p>
      <button type="button" onClick={openSettings}>
        Open Settings
      </button>
    </main>
  );
};
