/** Brand -> primary domain, used only to fetch a logo.
 *
 *  Presentation metadata, deliberately kept out of products.json and out of the
 *  pipeline: it has nothing to do with screening, and a missing logo must never
 *  be able to affect a verdict.
 */
const DOMAINS: Record<string, string> = {
  ring: "ring.com",
  blink: "blinkforhome.com",
  arlo: "arlo.com",
  wyze: "wyze.com",
  ezviz: "ezviz.com",
  reolink: "reolink.com",
  amcrest: "amcrest.com",
  eufy: "eufy.com",
  "tp-link": "tp-link.com",
  netgear: "netgear.com",
  asus: "asus.com",
  "d-link": "dlink.com",
  ubiquiti: "ui.com",
  tenda: "tendacn.com",
  irobot: "irobot.com",
  roborock: "roborock.com",
  ecovacs: "ecovacs.com",
  dreame: "dreametech.com",
  tcl: "tcl.com",
  hisense: "hisense.com",
  vizio: "vizio.com",
  sonos: "sonos.com",
  anker: "anker.com",
  govee: "govee.com",
  lutron: "lutron.com",
};

export function logoFor(productId: string): string | null {
  const domain = DOMAINS[productId];
  return domain
    ? `https://www.google.com/s2/favicons?domain=${domain}&sz=128`
    : null;
}
