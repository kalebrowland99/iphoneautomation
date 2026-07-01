export function getBrand(config = {}) {
  const raw = config.appId;
  if (raw === "valcoin") {
    return {
      appId: "valcoin",
      appName: "Valcoin",
      slideshowName: "Valcoin Slideshows",
      appLower: "valcoin",
      appCategory: "coinscan",
    };
  }
  if (raw === "labely") {
    return {
      appId: "labely",
      appName: "Labely",
      slideshowName: "Labely",
      appLower: "labely",
      appCategory: "foodscan",
    };
  }
  return {
    appId: "thrifty",
    appName: "Thrifty",
    slideshowName: "Thrifty Slideshows",
    appLower: "thrifty",
    appCategory: "reselling",
  };
}

