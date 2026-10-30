# Slug audit baseline — dev, 2026-08-19

Produced by `node scripts/marketing-content/08-check-slug-collisions.mjs`
against dev-dashboard.swibba.com BEFORE any schema change was applied.

This is the pre-existing state of base slugs in the live catalog. Every line
is a URL that would 404, resolve to the wrong entity, or shadow a modifier
facet once the /catalog/ resolver ships.

```

Marketing Content / 08 check-slug-collisions (read-only)
target: https://dev-dashboard.swibba.com
mode:   DRY RUN (no writes - pass --apply to commit)

category (categories)
--------------------------------------------
  11 rows
  . categories_translations.slug not present yet - run 01-apply-schema.mjs

subcategory (subcategories)
--------------------------------------------
  71 rows
  . subcategories_translations.slug not present yet - run 01-apply-schema.mjs

brand (brands)
--------------------------------------------
  210 rows
  . brands_translations.slug not present yet - run 01-apply-schema.mjs

series (series)
--------------------------------------------
  1056 rows
  x series "apple-watch--8" is not canonical - slugify gives "apple-watch-8"
  x series "apple-watch--9" is not canonical - slugify gives "apple-watch-9"
  x series "apple-watch--10" is not canonical - slugify gives "apple-watch-10"
  x series "p" collides with a RESERVED modifier token. It would shadow the condition or listing-type facet at that position.
  x series "lg-gram-+view" contains a character that breaks a URL path segment
  x series "lg-gram-+view" is not canonical - slugify gives "lg-gram-view"
  x series "ultragear-(gaming)" is not canonical - slugify gives "ultragear-gaming"
  x series "legion--(gaming)" is not canonical - slugify gives "legion-gaming"
  x series "alpha-(α)-mirrorless" is not canonical - slugify gives "alpha-α-mirrorless"
  x series "cinema-line-(fx-)" is not canonical - slugify gives "cinema-line-fx"
  x series "dell-p--(professional)" is not canonical - slugify gives "dell-p-professional"
  x series "dell-s--(standard)" is not canonical - slugify gives "dell-s-standard"
  x series "dell-usb-headphones-(enterprise)" is not canonical - slugify gives "dell-usb-headphones-enterprise"
  x series "lenovo-vibe--(legacy)" is not canonical - slugify gives "lenovo-vibe-legacy"
  x series "lenovo-l--monitors" is not canonical - slugify gives "lenovo-l-monitors"
  x series "lenovo-smart-watch--(legacy)" is not canonical - slugify gives "lenovo-smart-watch-legacy"
  x series "lenovo-legion-headsets-(gaming)" is not canonical - slugify gives "lenovo-legion-headsets-gaming"
  x series "asus-smart-networking-devices-(aimesh-ecosystem)" is not canonical - slugify gives "asus-smart-networking-devices-aimesh-ecosystem"
  x series "realme-gt--(flagship-performance)" is not canonical - slugify gives "realme-gt-flagship-performance"
  x series "realme-number--(11-12-13)" is not canonical - slugify gives "realme-number-11-12-13"
  x series "realme-narzo--(budget-gaming)" is not canonical - slugify gives "realme-narzo-budget-gaming"
  x series "realme-c--(entry-level)" is not canonical - slugify gives "realme-c-entry-level"
  x series "vivo-x--(flagship-camera-focus)" is not canonical - slugify gives "vivo-x-flagship-camera-focus"
  x series "vivo-v--(portrait-mid-premium)" is not canonical - slugify gives "vivo-v-portrait-mid-premium"
  x series "vivo-y--(budget-entry)" is not canonical - slugify gives "vivo-y-budget-entry"
  x series "vivo-t--(performance-gaming)" is not canonical - slugify gives "vivo-t-performance-gaming"
  x series "vivo-s--(selfie-focus)" is not canonical - slugify gives "vivo-s-selfie-focus"
  x series "iqoo--(performance-gaming)" is not canonical - slugify gives "iqoo-performance-gaming"
  x series "nokia-zeiss-camera-technology-(legacy-collaboration)" is not canonical - slugify gives "nokia-zeiss-camera-technology-legacy-collaboration"
  x series "surface-rt---surface-2" is not canonical - slugify gives "surface-rt-surface-2"
  x series "toshiba-smart-home-appliances-(iot)" is not canonical - slugify gives "toshiba-smart-home-appliances-iot"
  x series "sharp-r--(japan-market-devices)" is not canonical - slugify gives "sharp-r-japan-market-devices"
  x series "panasonic-p--(select-markets)" is not canonical - slugify gives "panasonic-p-select-markets"
  x series "panasonic-wearable-devices-(industrial)" is not canonical - slugify gives "panasonic-wearable-devices-industrial"
  x series "panasonic-dj---studio-headphones" is not canonical - slugify gives "panasonic-dj-studio-headphones"
  x series "playstation-vr-headsets-(ps-vr---ps-vr2)" is not canonical - slugify gives "playstation-vr-headsets-ps-vr-ps-vr2"
  x series "charging-stations-(dualsense-charging-dock)" is not canonical - slugify gives "charging-stations-dualsense-charging-dock"
  x series "gaming-headsets-(pulse-)" is not canonical - slugify gives "gaming-headsets-pulse"
  x series "playstation-gaming-earbuds-(pulse-explore)" is not canonical - slugify gives "playstation-gaming-earbuds-pulse-explore"
  x series "sony-home-theater-systems-(playstation-compatible)" is not canonical - slugify gives "sony-home-theater-systems-playstation-compatible"
  x series "sony-android-tablets-(legacy-support-devices)" is not canonical - slugify gives "sony-android-tablets-legacy-support-devices"
  x series "playstation-camera-(ps4)" is not canonical - slugify gives "playstation-camera-ps4"
  x series "xbox-wireless-controller-(core-)" is not canonical - slugify gives "xbox-wireless-controller-core"
  x series "xbox-kinect-(legacy-accessory)" is not canonical - slugify gives "xbox-kinect-legacy-accessory"
  x series "xbox-certified-4k---120hz-monitors" is not canonical - slugify gives "xbox-certified-4k-120hz-monitors"
  x series "hdmi-2.1-gaming-monitor" is not canonical - slugify gives "hdmi-21-gaming-monitor"
  x series "xbox-optimized-gaming-displays-(partner-brands)" is not canonical - slugify gives "xbox-optimized-gaming-displays-partner-brands"
  x series "xbox-gaming-earbuds-(partner-devices)" is not canonical - slugify gives "xbox-gaming-earbuds-partner-devices"
  x series "dolby-atmos-speaker-systems-(xbox-compatible)" is not canonical - slugify gives "dolby-atmos-speaker-systems-xbox-compatible"
  x series "windows-gaming-laptops-(xbox-integration)" is not canonical - slugify gives "windows-gaming-laptops-xbox-integration"
  x series "xbox-kinect-sensor-(legacy-motion-camera)" is not canonical - slugify gives "xbox-kinect-sensor-legacy-motion-camera"
  x series "xbox-network-services-(xbox-live---game-pass-cloud)" is not canonical - slugify gives "xbox-network-services-xbox-live-game-pass-cloud"
  x series "a-class" starts with a city prefix (a-) and would be parsed as a city segment
  x series "levi's-belts" is not canonical - slugify gives "levis-belts"
  x series "levi's-bags" is not canonical - slugify gives "levis-bags"
  x series "levi's-eyewear" is not canonical - slugify gives "levis-eyewear"
  x series "crisp-'n-bake" is not canonical - slugify gives "crisp-n-bake"
  x series "levi's-501" is not canonical - slugify gives "levis-501"
  x series "levi's-511" is not canonical - slugify gives "levis-511"
  x series "levi's-512" is not canonical - slugify gives "levis-512"
  x series "levi's-women-denim" is not canonical - slugify gives "levis-women-denim"
  . series_translations.slug not present yet - run 01-apply-schema.mjs

model (models)
--------------------------------------------
  3883 rows
  x model "jet-bot-ai+" contains a character that breaks a URL path segment
  x model "jet-bot-ai+" is not canonical - slugify gives "jet-bot-ai"
  x model "ipad-pro-11-(m2)" is not canonical - slugify gives "ipad-pro-11-m2"
  x model "ipad-pro-12.9-(m2)" is not canonical - slugify gives "ipad-pro-129-m2"
  x model "ipad-pro-11-(m4)" is not canonical - slugify gives "ipad-pro-11-m4"
  x model "ipad-pro-13-(m4)" is not canonical - slugify gives "ipad-pro-13-m4"
  x model "studio-display-(nano-texture)" is not canonical - slugify gives "studio-display-nano-texture"
  x model "pro-display-xdr-(pro-stand)" is not canonical - slugify gives "pro-display-xdr-pro-stand"
  x model "airpods-3-(rev)" is not canonical - slugify gives "airpods-3-rev"
  x model "airpods-pro-2-(usb-c)" is not canonical - slugify gives "airpods-pro-2-usb-c"
  x model "airpods-max-(usb-c)" is not canonical - slugify gives "airpods-max-usb-c"
  x model "homepod-2-(rev)" is not canonical - slugify gives "homepod-2-rev"
  x model "homepod-mini-(rev)" is not canonical - slugify gives "homepod-mini-rev"
  x model "matepad-pro-13.2" is not canonical - slugify gives "matepad-pro-132"
  x model "matepad-pro-13.2-(gen-2)" is not canonical - slugify gives "matepad-pro-132-gen-2"
  x model "matepad-air-11.5" is not canonical - slugify gives "matepad-air-115"
  x model "matepad-air-12-(gen-2)" is not canonical - slugify gives "matepad-air-12-gen-2"
  x model "matepad-11.5" is not canonical - slugify gives "matepad-115"
  x model "matepad-se-10.4" is not canonical - slugify gives "matepad-se-104"
  x model "matepad-se-11-(gen-2)" is not canonical - slugify gives "matepad-se-11-gen-2"
  x model "mateview-28-(rev)" is not canonical - slugify gives "mateview-28-rev"
  x model "mateview-gt-34-(rev)" is not canonical - slugify gives "mateview-gt-34-rev"
  x model "lg-g-pad-5-10.1" is not canonical - slugify gives "lg-g-pad-5-101"
  x model "lg-gram-+view-16" contains a character that breaks a URL path segment
  x model "lg-gram-+view-16" is not canonical - slugify gives "lg-gram-view-16"
  x model "lg-gram-+view-16-(rev)" contains a character that breaks a URL path segment
  x model "lg-gram-+view-16-(rev)" is not canonical - slugify gives "lg-gram-view-16-rev"
  x model "lg-gram-+view-ai" contains a character that breaks a URL path segment
  x model "lg-gram-+view-ai" is not canonical - slugify gives "lg-gram-view-ai"
  x model "lenovo-legion-tab-8.8" is not canonical - slugify gives "lenovo-legion-tab-88"
  x model base slug "s24" is duplicated in scope b2ea4c3f-8f10-4aee-ba99-a8a21ef1b240 (ids a858237c-0dfd-4821-bc3b-da74c5f27854 and a858237c-0dfd-4821-bc3b-da74c5f27854)
  x model "nokia-8.3-5g" is not canonical - slugify gives "nokia-83-5g"
  x model "sharp-sound-bar-sb-2.0" is not canonical - slugify gives "sharp-sound-bar-sb-20"
  x model "sharp-sound-bar-sb-3.1" is not canonical - slugify gives "sharp-sound-bar-sb-31"
  x model "sharp-sound-bar-ai-sb-3.1" is not canonical - slugify gives "sharp-sound-bar-ai-sb-31"
  x model "sharp-sound-bar-ai-ultra-sb-5.1" is not canonical - slugify gives "sharp-sound-bar-ai-ultra-sb-51"
  x model "sharp-home-theater-ht-5.1" is not canonical - slugify gives "sharp-home-theater-ht-51"
  x model "sharp-home-theater-ht-7.1" is not canonical - slugify gives "sharp-home-theater-ht-71"
  x model "sharp-home-theater-ai-ht-7.1" is not canonical - slugify gives "sharp-home-theater-ai-ht-71"
  x model "sharp-home-theater-ai-ultra-ht-9.1" is not canonical - slugify gives "sharp-home-theater-ai-ultra-ht-91"
  x model "philips-android-tablet-7"-ics-series" is not canonical - slugify gives "philips-android-tablet-7-ics-series"
  x model base slug "s24" is duplicated in scope b2ea4c3f-8f10-4aee-ba99-a8a21ef1b240 (ids a858237c-0dfd-4821-bc3b-da74c5f27854 and a858237c-0dfd-4821-bc3b-da74c5f27854)
  x model "philips-hue-white-&-color-starter-kit" contains a character that breaks a URL path segment
  x model "philips-hue-white-&-color-starter-kit" is not canonical - slugify gives "philips-hue-white-color-starter-kit"
  x model "playstation-vr-(ps-vr)" is not canonical - slugify gives "playstation-vr-ps-vr"
  x model "playstation-camera-(ps4)" is not canonical - slugify gives "playstation-camera-ps4"
  x model "playstation-remote-play-mobile-(ios/android)" contains a character that breaks a URL path segment
  x model "playstation-remote-play-mobile-(ios/android)" is not canonical - slugify gives "playstation-remote-play-mobile-iosandroid"
  x model "xbox-wireless-controller-(xbox-one-gen-1)" is not canonical - slugify gives "xbox-wireless-controller-xbox-one-gen-1"
  x model "xbox-wireless-controller-(bluetooth-edition)" is not canonical - slugify gives "xbox-wireless-controller-bluetooth-edition"
  x model "xbox-special-edition-controller-(cyberpunk)" is not canonical - slugify gives "xbox-special-edition-controller-cyberpunk"
  x model "xbox-play-&-charge-kit" contains a character that breaks a URL path segment
  x model "xbox-play-&-charge-kit" is not canonical - slugify gives "xbox-play-charge-kit"
  x model "lg-27gn950-hdmi-2.1-edition" is not canonical - slugify gives "lg-27gn950-hdmi-21-edition"
  x model "samsung-odyssey-g7-hdmi-2.1" is not canonical - slugify gives "samsung-odyssey-g7-hdmi-21"
  x model "xbox-cloud-gaming-(xcloud-mobile-app)" is not canonical - slugify gives "xbox-cloud-gaming-xcloud-mobile-app"
  x model "markus-office-chair-(updated-edition)" is not canonical - slugify gives "markus-office-chair-updated-edition"
  x model "järvfjället-office-chair-(rev-a)" is not canonical - slugify gives "järvfjället-office-chair-rev-a"
  x model "poäng-armchair-(modern-cushion-update)" is not canonical - slugify gives "poäng-armchair-modern-cushion-update"
  x model "ingolf-dining-chair-(reinforced)" is not canonical - slugify gives "ingolf-dining-chair-reinforced"
  x model "klippan-2-seater-sofa-(updated-fabric)" is not canonical - slugify gives "klippan-2-seater-sofa-updated-fabric"
  x model "bekant-sit/stand-desk" contains a character that breaks a URL path segment
  x model "bekant-sit/stand-desk" is not canonical - slugify gives "bekant-sitstand-desk"
  x model "dining-chair-set-(4-pcs)" is not canonical - slugify gives "dining-chair-set-4-pcs"
  x model "luxury-sofa-set-3+2+1" contains a character that breaks a URL path segment
  x model "luxury-sofa-set-3+2+1" is not canonical - slugify gives "luxury-sofa-set-321"
  x model "puma-essentials+-full-zip" contains a character that breaks a URL path segment
  x model "puma-essentials+-full-zip" is not canonical - slugify gives "puma-essentials-full-zip"
  x model "puma-essentials+-oversized-hoodie" contains a character that breaks a URL path segment
  x model "puma-essentials+-oversized-hoodie" is not canonical - slugify gives "puma-essentials-oversized-hoodie"
  x model "puma-essentials-re:suede-tee" is not canonical - slugify gives "puma-essentials-resuede-tee"
  x model "puma-suede-re:suede" is not canonical - slugify gives "puma-suede-resuede"
  x model "pull&bear-slip-on" contains a character that breaks a URL path segment
  x model "pull&bear-slip-on" is not canonical - slugify gives "pullbear-slip-on"
  x model "pull&bear-graphic-tee" contains a character that breaks a URL path segment
  x model "pull&bear-graphic-tee" is not canonical - slugify gives "pullbear-graphic-tee"
  x model "pull&bear-oversized-hoodie" contains a character that breaks a URL path segment
  x model "pull&bear-oversized-hoodie" is not canonical - slugify gives "pullbear-oversized-hoodie"
  x model "pull&bear-cargo-joggers" contains a character that breaks a URL path segment
  x model "pull&bear-cargo-joggers" is not canonical - slugify gives "pullbear-cargo-joggers"
  x model "pull&bear-bomber-jacket" contains a character that breaks a URL path segment
  x model "pull&bear-bomber-jacket" is not canonical - slugify gives "pullbear-bomber-jacket"
  x model "pull&bear-tie-dye-tee" contains a character that breaks a URL path segment
  x model "pull&bear-tie-dye-tee" is not canonical - slugify gives "pullbear-tie-dye-tee"
  x model "pull&bear-tech-windbreaker" contains a character that breaks a URL path segment
  x model "pull&bear-tech-windbreaker" is not canonical - slugify gives "pullbear-tech-windbreaker"
  x model "pull&bear-oversized-shirt" contains a character that breaks a URL path segment
  x model "pull&bear-oversized-shirt" is not canonical - slugify gives "pullbear-oversized-shirt"
  x model "pull&bear-utility-vest" contains a character that breaks a URL path segment
  x model "pull&bear-utility-vest" is not canonical - slugify gives "pullbear-utility-vest"
  x model "pull&bear-eco-hoodie" contains a character that breaks a URL path segment
  x model "pull&bear-eco-hoodie" is not canonical - slugify gives "pullbear-eco-hoodie"
  x model "pull&bear-premium-street-jacket" contains a character that breaks a URL path segment
  x model "pull&bear-premium-street-jacket" is not canonical - slugify gives "pullbear-premium-street-jacket"
  x model "pull&bear-slim-jeans" contains a character that breaks a URL path segment
  x model "pull&bear-slim-jeans" is not canonical - slugify gives "pullbear-slim-jeans"
  x model "pull&bear-relaxed-jeans" contains a character that breaks a URL path segment
  x model "pull&bear-relaxed-jeans" is not canonical - slugify gives "pullbear-relaxed-jeans"
  x model "pull&bear-denim-jacket" contains a character that breaks a URL path segment
  x model "pull&bear-denim-jacket" is not canonical - slugify gives "pullbear-denim-jacket"
  x model "pull&bear-ripped-skinny-jeans" contains a character that breaks a URL path segment
  x model "pull&bear-ripped-skinny-jeans" is not canonical - slugify gives "pullbear-ripped-skinny-jeans"
  x model "pull&bear-cargo-jeans" contains a character that breaks a URL path segment
  x model "pull&bear-cargo-jeans" is not canonical - slugify gives "pullbear-cargo-jeans"
  x model "pull&bear-wide-leg-jeans" contains a character that breaks a URL path segment
  x model "pull&bear-wide-leg-jeans" is not canonical - slugify gives "pullbear-wide-leg-jeans"
  x model "pull&bear-eco-denim-jeans" contains a character that breaks a URL path segment
  x model "pull&bear-eco-denim-jeans" is not canonical - slugify gives "pullbear-eco-denim-jeans"
  x model "pull&bear-carpenter-jeans" contains a character that breaks a URL path segment
  x model "pull&bear-carpenter-jeans" is not canonical - slugify gives "pullbear-carpenter-jeans"
  x model "pull&bear-premium-selvedge" contains a character that breaks a URL path segment
  x model "pull&bear-premium-selvedge" is not canonical - slugify gives "pullbear-premium-selvedge"
  x model "pull&bear-stretch-comfort-jeans" contains a character that breaks a URL path segment
  x model "pull&bear-stretch-comfort-jeans" is not canonical - slugify gives "pullbear-stretch-comfort-jeans"
  x model "pull&bear-crop-top" contains a character that breaks a URL path segment
  x model "pull&bear-crop-top" is not canonical - slugify gives "pullbear-crop-top"
  x model "pull&bear-oversized-tee" contains a character that breaks a URL path segment
  x model "pull&bear-oversized-tee" is not canonical - slugify gives "pullbear-oversized-tee"
  x model "pull&bear-wide-leg-pants" contains a character that breaks a URL path segment
  x model "pull&bear-wide-leg-pants" is not canonical - slugify gives "pullbear-wide-leg-pants"
  x model "pull&bear-cargo-pants" contains a character that breaks a URL path segment
  x model "pull&bear-cargo-pants" is not canonical - slugify gives "pullbear-cargo-pants"
  x model "pull&bear-hoodie-dress" contains a character that breaks a URL path segment
  x model "pull&bear-hoodie-dress" is not canonical - slugify gives "pullbear-hoodie-dress"
  x model "pull&bear-denim-mini-skirt" contains a character that breaks a URL path segment
  x model "pull&bear-denim-mini-skirt" is not canonical - slugify gives "pullbear-denim-mini-skirt"
  x model "pull&bear-utility-jacket" contains a character that breaks a URL path segment
  x model "pull&bear-utility-jacket" is not canonical - slugify gives "pullbear-utility-jacket"
  x model "pull&bear-parachute-pants" contains a character that breaks a URL path segment
  x model "pull&bear-parachute-pants" is not canonical - slugify gives "pullbear-parachute-pants"
  x model "pull&bear-corset-top" contains a character that breaks a URL path segment
  x model "pull&bear-corset-top" is not canonical - slugify gives "pullbear-corset-top"
  x model "pull&bear-eco-coord-set" contains a character that breaks a URL path segment
  x model "pull&bear-eco-coord-set" is not canonical - slugify gives "pullbear-eco-coord-set"
  x model "pull&bear-basic-canvas" contains a character that breaks a URL path segment
  x model "pull&bear-basic-canvas" is not canonical - slugify gives "pullbear-basic-canvas"
  x model "pull&bear-platform-sneaker" contains a character that breaks a URL path segment
  x model "pull&bear-platform-sneaker" is not canonical - slugify gives "pullbear-platform-sneaker"
  x model "pull&bear-retro-runner" contains a character that breaks a URL path segment
  x model "pull&bear-retro-runner" is not canonical - slugify gives "pullbear-retro-runner"
  x model "pull&bear-high-top-canvas" contains a character that breaks a URL path segment
  x model "pull&bear-high-top-canvas" is not canonical - slugify gives "pullbear-high-top-canvas"
  x model "pull&bear-chunky-sneaker" contains a character that breaks a URL path segment
  x model "pull&bear-chunky-sneaker" is not canonical - slugify gives "pullbear-chunky-sneaker"
  x model "pull&bear-skate-sneaker" contains a character that breaks a URL path segment
  x model "pull&bear-skate-sneaker" is not canonical - slugify gives "pullbear-skate-sneaker"
  x model "pull&bear-eco-sneaker" contains a character that breaks a URL path segment
  x model "pull&bear-eco-sneaker" is not canonical - slugify gives "pullbear-eco-sneaker"
  x model "pull&bear-premium-leather" contains a character that breaks a URL path segment
  x model "pull&bear-premium-leather" is not canonical - slugify gives "pullbear-premium-leather"
  x model "pull&bear-basic-backpack" contains a character that breaks a URL path segment
  x model "pull&bear-basic-backpack" is not canonical - slugify gives "pullbear-basic-backpack"
  x model "pull&bear-crossbody-bag" contains a character that breaks a URL path segment
  x model "pull&bear-crossbody-bag" is not canonical - slugify gives "pullbear-crossbody-bag"
  x model "pull&bear-canvas-tote" contains a character that breaks a URL path segment
  x model "pull&bear-canvas-tote" is not canonical - slugify gives "pullbear-canvas-tote"
  x model "pull&bear-mini-backpack" contains a character that breaks a URL path segment
  x model "pull&bear-mini-backpack" is not canonical - slugify gives "pullbear-mini-backpack"
  x model "pull&bear-belt-bag" contains a character that breaks a URL path segment
  x model "pull&bear-belt-bag" is not canonical - slugify gives "pullbear-belt-bag"
  x model "pull&bear-laptop-backpack" contains a character that breaks a URL path segment
  x model "pull&bear-laptop-backpack" is not canonical - slugify gives "pullbear-laptop-backpack"
  x model "pull&bear-bucket-bag" contains a character that breaks a URL path segment
  x model "pull&bear-bucket-bag" is not canonical - slugify gives "pullbear-bucket-bag"
  x model "pull&bear-eco-tote" contains a character that breaks a URL path segment
  x model "pull&bear-eco-tote" is not canonical - slugify gives "pullbear-eco-tote"
  x model "pull&bear-convertible-bag" contains a character that breaks a URL path segment
  x model "pull&bear-convertible-bag" is not canonical - slugify gives "pullbear-convertible-bag"
  x model "h&m-basic-t-shirt" contains a character that breaks a URL path segment
  x model "h&m-basic-t-shirt" is not canonical - slugify gives "hm-basic-t-shirt"
  x model "h&m-basic-sweater" contains a character that breaks a URL path segment
  x model "h&m-basic-sweater" is not canonical - slugify gives "hm-basic-sweater"
  x model "h&m-basic-jeans" contains a character that breaks a URL path segment
  x model "h&m-basic-jeans" is not canonical - slugify gives "hm-basic-jeans"
  x model "h&m-basic-chinos" contains a character that breaks a URL path segment
  x model "h&m-basic-chinos" is not canonical - slugify gives "hm-basic-chinos"
  x model "h&m-basic-essentials-set" contains a character that breaks a URL path segment
  x model "h&m-basic-essentials-set" is not canonical - slugify gives "hm-basic-essentials-set"
  x model "h&m-casual-polo" contains a character that breaks a URL path segment
  x model "h&m-casual-polo" is not canonical - slugify gives "hm-casual-polo"
  x model "h&m-casual-shirt" contains a character that breaks a URL path segment
  x model "h&m-casual-shirt" is not canonical - slugify gives "hm-casual-shirt"
  x model "h&m-casual-shorts" contains a character that breaks a URL path segment
  x model "h&m-casual-shorts" is not canonical - slugify gives "hm-casual-shorts"
  x model "h&m-casual-jacket" contains a character that breaks a URL path segment
  x model "h&m-casual-jacket" is not canonical - slugify gives "hm-casual-jacket"
  x model "h&m-casual-complete-outfit" contains a character that breaks a URL path segment
  x model "h&m-casual-complete-outfit" is not canonical - slugify gives "hm-casual-complete-outfit"
  x model "h&m-divided-t-shirt" contains a character that breaks a URL path segment
  x model "h&m-divided-t-shirt" is not canonical - slugify gives "hm-divided-t-shirt"
  x model "h&m-divided-hoodie" contains a character that breaks a URL path segment
  x model "h&m-divided-hoodie" is not canonical - slugify gives "hm-divided-hoodie"
  x model "h&m-divided-jeans" contains a character that breaks a URL path segment
  x model "h&m-divided-jeans" is not canonical - slugify gives "hm-divided-jeans"
  x model "h&m-divided-dress" contains a character that breaks a URL path segment
  x model "h&m-divided-dress" is not canonical - slugify gives "hm-divided-dress"
  x model "h&m-divided-complete-set" contains a character that breaks a URL path segment
  x model "h&m-divided-complete-set" is not canonical - slugify gives "hm-divided-complete-set"
  x model "h&m-studio-blouse" contains a character that breaks a URL path segment
  x model "h&m-studio-blouse" is not canonical - slugify gives "hm-studio-blouse"
  x model "h&m-studio-pants" contains a character that breaks a URL path segment
  x model "h&m-studio-pants" is not canonical - slugify gives "hm-studio-pants"
  x model "h&m-studio-blazer" contains a character that breaks a URL path segment
  x model "h&m-studio-blazer" is not canonical - slugify gives "hm-studio-blazer"
  x model "h&m-studio-dress" contains a character that breaks a URL path segment
  x model "h&m-studio-dress" is not canonical - slugify gives "hm-studio-dress"
  x model "h&m-studio-premium-set" contains a character that breaks a URL path segment
  x model "h&m-studio-premium-set" is not canonical - slugify gives "hm-studio-premium-set"
  x model "h&m-canvas-sneaker" contains a character that breaks a URL path segment
  x model "h&m-canvas-sneaker" is not canonical - slugify gives "hm-canvas-sneaker"
  x model "h&m-leather-sneaker" contains a character that breaks a URL path segment
  x model "h&m-leather-sneaker" is not canonical - slugify gives "hm-leather-sneaker"
  x model "h&m-slip-on-sneaker" contains a character that breaks a URL path segment
  x model "h&m-slip-on-sneaker" is not canonical - slugify gives "hm-slip-on-sneaker"
  x model "h&m-sport-sneaker" contains a character that breaks a URL path segment
  x model "h&m-sport-sneaker" is not canonical - slugify gives "hm-sport-sneaker"
  x model "h&m-trendy-sneaker" contains a character that breaks a URL path segment
  x model "h&m-trendy-sneaker" is not canonical - slugify gives "hm-trendy-sneaker"
  x model "h&m-casual-backpack" contains a character that breaks a URL path segment
  x model "h&m-casual-backpack" is not canonical - slugify gives "hm-casual-backpack"
  x model "h&m-crossbody-bag" contains a character that breaks a URL path segment
  x model "h&m-crossbody-bag" is not canonical - slugify gives "hm-crossbody-bag"
  x model "h&m-tote-bag" contains a character that breaks a URL path segment
  x model "h&m-tote-bag" is not canonical - slugify gives "hm-tote-bag"
  x model "h&m-duffle-bag" contains a character that breaks a URL path segment
  x model "h&m-duffle-bag" is not canonical - slugify gives "hm-duffle-bag"
  x model "h&m-shoulder-bag" contains a character that breaks a URL path segment
  x model "h&m-shoulder-bag" is not canonical - slugify gives "hm-shoulder-bag"
  x model "h&m-baseball-cap" contains a character that breaks a URL path segment
  x model "h&m-baseball-cap" is not canonical - slugify gives "hm-baseball-cap"
  x model "h&m-trucker-cap" contains a character that breaks a URL path segment
  x model "h&m-trucker-cap" is not canonical - slugify gives "hm-trucker-cap"
  x model "h&m-beanie" contains a character that breaks a URL path segment
  x model "h&m-beanie" is not canonical - slugify gives "hm-beanie"
  x model "h&m-dad-hat" contains a character that breaks a URL path segment
  x model "h&m-dad-hat" is not canonical - slugify gives "hm-dad-hat"
  x model "h&m-premium-cap" contains a character that breaks a URL path segment
  x model "h&m-premium-cap" is not canonical - slugify gives "hm-premium-cap"
  x model "crisp-'n-bake-2.5l" is not canonical - slugify gives "crisp-n-bake-25l"
  x model "crisp-'n-bake-3.5l" is not canonical - slugify gives "crisp-n-bake-35l"
  x model "crisp-'n-bake-4.5l-pro" is not canonical - slugify gives "crisp-n-bake-45l-pro"
  x model "crisp-'n-bake-smart-3.5l" is not canonical - slugify gives "crisp-n-bake-smart-35l"
  x model "crisp-'n-bake-ai-5l" is not canonical - slugify gives "crisp-n-bake-ai-5l"
  x model "braun-brewsense-grind-&-brew" contains a character that breaks a URL path segment
  x model "braun-brewsense-grind-&-brew" is not canonical - slugify gives "braun-brewsense-grind-brew"
  x model "philips-senseo-original+-2022" contains a character that breaks a URL path segment
  x model "philips-senseo-original+-2022" is not canonical - slugify gives "philips-senseo-original-2022"
  x model "philips-aquatrio-max+-2025" contains a character that breaks a URL path segment
  x model "philips-aquatrio-max+-2025" is not canonical - slugify gives "philips-aquatrio-max-2025"
  x model "skoda-octavia-1.0-tsi" is not canonical - slugify gives "skoda-octavia-10-tsi"
  x model "skoda-octavia-1.5-tsi" is not canonical - slugify gives "skoda-octavia-15-tsi"
  x model "skoda-octavia-2.0-tdi" is not canonical - slugify gives "skoda-octavia-20-tdi"
  x model "skoda-octavia-1.5-tsi-iv" is not canonical - slugify gives "skoda-octavia-15-tsi-iv"
  x model "skoda-octavia-rs-2.0-tsi" is not canonical - slugify gives "skoda-octavia-rs-20-tsi"
  x model "skoda-superb-2.0-tsi" is not canonical - slugify gives "skoda-superb-20-tsi"
  x model "skoda-superb-2.0-tdi-4x4" is not canonical - slugify gives "skoda-superb-20-tdi-4x4"
  x model "skoda-superb-1.5-tsi-iv" is not canonical - slugify gives "skoda-superb-15-tsi-iv"
  x model "skoda-superb-l&k-2.0-tsi" contains a character that breaks a URL path segment
  x model "skoda-superb-l&k-2.0-tsi" is not canonical - slugify gives "skoda-superb-lk-20-tsi"
  x model "skoda-superb-sportline-2.0-tsi" is not canonical - slugify gives "skoda-superb-sportline-20-tsi"
  x model "skoda-fabia-1.0-mpi" is not canonical - slugify gives "skoda-fabia-10-mpi"
  x model "skoda-fabia-1.0-tsi" is not canonical - slugify gives "skoda-fabia-10-tsi"
  x model "skoda-fabia-1.5-tsi" is not canonical - slugify gives "skoda-fabia-15-tsi"
  x model "skoda-fabia-monte-carlo-1.5-tsi" is not canonical - slugify gives "skoda-fabia-monte-carlo-15-tsi"
  x model "skoda-fabia-rs-2.0-tsi" is not canonical - slugify gives "skoda-fabia-rs-20-tsi"
  x model "skoda-kodiaq-1.5-tsi" is not canonical - slugify gives "skoda-kodiaq-15-tsi"
  x model "skoda-kodiaq-2.0-tdi-4x4" is not canonical - slugify gives "skoda-kodiaq-20-tdi-4x4"
  x model "skoda-kodiaq-1.5-tsi-iv" is not canonical - slugify gives "skoda-kodiaq-15-tsi-iv"
  x model "skoda-kodiaq-l&k-2.0-tsi-4x4" contains a character that breaks a URL path segment
  x model "skoda-kodiaq-l&k-2.0-tsi-4x4" is not canonical - slugify gives "skoda-kodiaq-lk-20-tsi-4x4"
  x model "skoda-kodiaq-rs-2.0-tsi-4x4" is not canonical - slugify gives "skoda-kodiaq-rs-20-tsi-4x4"
  x model "skoda-karoq-1.0-tsi" is not canonical - slugify gives "skoda-karoq-10-tsi"
  x model "skoda-karoq-1.5-tsi" is not canonical - slugify gives "skoda-karoq-15-tsi"
  x model "skoda-karoq-2.0-tdi-4x4" is not canonical - slugify gives "skoda-karoq-20-tdi-4x4"
  x model "skoda-karoq-1.5-tsi-iv" is not canonical - slugify gives "skoda-karoq-15-tsi-iv"
  x model "skoda-karoq-sportline-2.0-tsi-4x4" is not canonical - slugify gives "skoda-karoq-sportline-20-tsi-4x4"
  x model "tefal-actifry-genius+-ah9800" contains a character that breaks a URL path segment
  x model "tefal-actifry-genius+-ah9800" is not canonical - slugify gives "tefal-actifry-genius-ah9800"
  x model "levi's-501-original-fit-jeans" is not canonical - slugify gives "levis-501-original-fit-jeans"
  x model "levi's-501-'54-jeans" is not canonical - slugify gives "levis-501-54-jeans"
  x model "levi's-501-crop-jeans" is not canonical - slugify gives "levis-501-crop-jeans"
  x model "levi's-501-bettercotton-jeans" is not canonical - slugify gives "levis-501-bettercotton-jeans"
  x model "levi's-501-premium-selvedge" is not canonical - slugify gives "levis-501-premium-selvedge"
  x model "levi's-511-slim-fit-jeans" is not canonical - slugify gives "levis-511-slim-fit-jeans"
  x model "levi's-511-hybrid-trouser" is not canonical - slugify gives "levis-511-hybrid-trouser"
  x model "levi's-511-eco-performance-slim" is not canonical - slugify gives "levis-511-eco-performance-slim"
  x model "levi's-511-slim-taper-jeans" is not canonical - slugify gives "levis-511-slim-taper-jeans"
  x model "levi's-511-stretch-premium-slim" is not canonical - slugify gives "levis-511-stretch-premium-slim"
  x model "levi's-512-slim-taper-jeans" is not canonical - slugify gives "levis-512-slim-taper-jeans"
  x model "levi's-512-flex-taper-jeans" is not canonical - slugify gives "levis-512-flex-taper-jeans"
  x model "levi's-512-eco-taper" is not canonical - slugify gives "levis-512-eco-taper"
  x model "levi's-512-cargo-taper-jeans" is not canonical - slugify gives "levis-512-cargo-taper-jeans"
  x model "levi's-512-premium-stretch-taper" is not canonical - slugify gives "levis-512-premium-stretch-taper"
  x model "levi's-724-high-rise-straight-jeans" is not canonical - slugify gives "levis-724-high-rise-straight-jeans"
  x model "levi's-720-high-rise-super-skinny" is not canonical - slugify gives "levis-720-high-rise-super-skinny"
  x model "levi's-501-women's-jeans" is not canonical - slugify gives "levis-501-womens-jeans"
  x model "levi's-ribcage-wide-leg-jeans" is not canonical - slugify gives "levis-ribcage-wide-leg-jeans"
  x model "levi's-women's-baggy-dad-jeans" is not canonical - slugify gives "levis-womens-baggy-dad-jeans"
  x model "levi's-classic-logo-belt" is not canonical - slugify gives "levis-classic-logo-belt"
  x model "levi's-reversible-leather-belt" is not canonical - slugify gives "levis-reversible-leather-belt"
  x model "levi's-women-braided-belt" is not canonical - slugify gives "levis-women-braided-belt"
  x model "levi's-bettercotton-canvas-belt" is not canonical - slugify gives "levis-bettercotton-canvas-belt"
  x model "levi's-premium-full-grain-leather-belt" is not canonical - slugify gives "levis-premium-full-grain-leather-belt"
  x model "levi's-mini-backpack" is not canonical - slugify gives "levis-mini-backpack"
  x model "levi's-tote-bag" is not canonical - slugify gives "levis-tote-bag"
  x model "levi's-sling-crossbody-bag" is not canonical - slugify gives "levis-sling-crossbody-bag"
  x model "levi's-denim-shoulder-bag" is not canonical - slugify gives "levis-denim-shoulder-bag"
  x model "levi's-premium-leather-messenger" is not canonical - slugify gives "levis-premium-leather-messenger"
  x model "levi's-lv-5002-wayfarers" is not canonical - slugify gives "levis-lv-5002-wayfarers"
  x model "levi's-lv-5009-aviator-sunglasses" is not canonical - slugify gives "levis-lv-5009-aviator-sunglasses"
  x model "levi's-lv-5023-square-acetate" is not canonical - slugify gives "levis-lv-5023-square-acetate"
  x model "levi's-lv-5040-retro-round" is not canonical - slugify gives "levis-lv-5040-retro-round"
  x model "levi's-lv-5060-sport-wrap" is not canonical - slugify gives "levis-lv-5060-sport-wrap"
  x model "levi's-501-original-fit-jeans-1" is not canonical - slugify gives "levis-501-original-fit-jeans-1"
  x model "levi's-501-'54-jeans-1" is not canonical - slugify gives "levis-501-54-jeans-1"
  x model "levi's-501-crop-jeans-1" is not canonical - slugify gives "levis-501-crop-jeans-1"
  x model "levi's-501-bettercotton-jeans-1" is not canonical - slugify gives "levis-501-bettercotton-jeans-1"
  x model "levi's-501-premium-selvedge-1" is not canonical - slugify gives "levis-501-premium-selvedge-1"
  x model "levi's-511-slim-fit-jeans-1" is not canonical - slugify gives "levis-511-slim-fit-jeans-1"
  x model "levi's-511-hybrid-trouser-1" is not canonical - slugify gives "levis-511-hybrid-trouser-1"
  x model "levi's-511-eco-performance-slim-1" is not canonical - slugify gives "levis-511-eco-performance-slim-1"
  x model "levi's-511-slim-taper-jeans-1" is not canonical - slugify gives "levis-511-slim-taper-jeans-1"
  x model "levi's-511-stretch-premium-slim-1" is not canonical - slugify gives "levis-511-stretch-premium-slim-1"
  x model "levi's-512-slim-taper-jeans-1" is not canonical - slugify gives "levis-512-slim-taper-jeans-1"
  x model "levi's-512-flex-taper-jeans-1" is not canonical - slugify gives "levis-512-flex-taper-jeans-1"
  x model "levi's-512-eco-taper-1" is not canonical - slugify gives "levis-512-eco-taper-1"
  x model "levi's-512-cargo-taper-jeans-1" is not canonical - slugify gives "levis-512-cargo-taper-jeans-1"
  x model "levi's-512-premium-stretch-taper-1" is not canonical - slugify gives "levis-512-premium-stretch-taper-1"
  x model "levi's-724-high-rise-straight-jeans-1" is not canonical - slugify gives "levis-724-high-rise-straight-jeans-1"
  x model "levi's-720-high-rise-super-skinny-1" is not canonical - slugify gives "levis-720-high-rise-super-skinny-1"
  x model "levi's-501-women's-jeans-1" is not canonical - slugify gives "levis-501-womens-jeans-1"
  x model "levi's-ribcage-wide-leg-jeans-1" is not canonical - slugify gives "levis-ribcage-wide-leg-jeans-1"
  x model "levi's-women's-baggy-dad-jeans-1" is not canonical - slugify gives "levis-womens-baggy-dad-jeans-1"
  x model "levi's-classic-logo-belt-1" is not canonical - slugify gives "levis-classic-logo-belt-1"
  x model "levi's-reversible-leather-belt-1" is not canonical - slugify gives "levis-reversible-leather-belt-1"
  x model "levi's-women-braided-belt-1" is not canonical - slugify gives "levis-women-braided-belt-1"
  x model "levi's-bettercotton-canvas-belt-1" is not canonical - slugify gives "levis-bettercotton-canvas-belt-1"
  x model "levi's-premium-full-grain-leather-belt-1" is not canonical - slugify gives "levis-premium-full-grain-leather-belt-1"
  x model "levi's-mini-backpack-1" is not canonical - slugify gives "levis-mini-backpack-1"
  x model "levi's-tote-bag-1" is not canonical - slugify gives "levis-tote-bag-1"
  x model "levi's-sling-crossbody-bag-1" is not canonical - slugify gives "levis-sling-crossbody-bag-1"
  x model "levi's-denim-shoulder-bag-1" is not canonical - slugify gives "levis-denim-shoulder-bag-1"
  x model "levi's-premium-leather-messenger-1" is not canonical - slugify gives "levis-premium-leather-messenger-1"
  x model "levi's-lv-5002-wayfarers-1" is not canonical - slugify gives "levis-lv-5002-wayfarers-1"
  x model "levi's-lv-5009-aviator-sunglasses-1" is not canonical - slugify gives "levis-lv-5009-aviator-sunglasses-1"
  x model "levi's-lv-5023-square-acetate-1" is not canonical - slugify gives "levis-lv-5023-square-acetate-1"
  x model "levi's-lv-5040-retro-round-1" is not canonical - slugify gives "levis-lv-5040-retro-round-1"
  x model "levi's-lv-5060-sport-wrap-1" is not canonical - slugify gives "levis-lv-5060-sport-wrap-1"
  x model "skoda-octavia-1.0-tsi-1" is not canonical - slugify gives "skoda-octavia-10-tsi-1"
  x model "skoda-octavia-1.5-tsi-1" is not canonical - slugify gives "skoda-octavia-15-tsi-1"
  x model "skoda-octavia-2.0-tdi-1" is not canonical - slugify gives "skoda-octavia-20-tdi-1"
  x model "skoda-octavia-1.5-tsi-iv-1" is not canonical - slugify gives "skoda-octavia-15-tsi-iv-1"
  x model "skoda-octavia-rs-2.0-tsi-1" is not canonical - slugify gives "skoda-octavia-rs-20-tsi-1"
  x model "skoda-superb-2.0-tsi-1" is not canonical - slugify gives "skoda-superb-20-tsi-1"
  x model "skoda-superb-2.0-tdi-4x4-1" is not canonical - slugify gives "skoda-superb-20-tdi-4x4-1"
  x model "skoda-superb-1.5-tsi-iv-1" is not canonical - slugify gives "skoda-superb-15-tsi-iv-1"
  x model "skoda-superb-l&k-2.0-tsi-1" contains a character that breaks a URL path segment
  x model "skoda-superb-l&k-2.0-tsi-1" is not canonical - slugify gives "skoda-superb-lk-20-tsi-1"
  x model "skoda-superb-sportline-2.0-tsi-1" is not canonical - slugify gives "skoda-superb-sportline-20-tsi-1"
  x model "skoda-fabia-1.0-mpi-1" is not canonical - slugify gives "skoda-fabia-10-mpi-1"
  x model "skoda-fabia-1.0-tsi-1" is not canonical - slugify gives "skoda-fabia-10-tsi-1"
  x model "skoda-fabia-1.5-tsi-1" is not canonical - slugify gives "skoda-fabia-15-tsi-1"
  x model "skoda-fabia-monte-carlo-1.5-tsi-1" is not canonical - slugify gives "skoda-fabia-monte-carlo-15-tsi-1"
  x model "skoda-fabia-rs-2.0-tsi-1" is not canonical - slugify gives "skoda-fabia-rs-20-tsi-1"
  x model "skoda-kodiaq-1.5-tsi-1" is not canonical - slugify gives "skoda-kodiaq-15-tsi-1"
  x model "skoda-kodiaq-2.0-tdi-4x4-1" is not canonical - slugify gives "skoda-kodiaq-20-tdi-4x4-1"
  x model "skoda-kodiaq-1.5-tsi-iv-1" is not canonical - slugify gives "skoda-kodiaq-15-tsi-iv-1"
  x model "skoda-kodiaq-l&k-2.0-tsi-4x4-1" contains a character that breaks a URL path segment
  x model "skoda-kodiaq-l&k-2.0-tsi-4x4-1" is not canonical - slugify gives "skoda-kodiaq-lk-20-tsi-4x4-1"
  x model "skoda-kodiaq-rs-2.0-tsi-4x4-1" is not canonical - slugify gives "skoda-kodiaq-rs-20-tsi-4x4-1"
  x model "skoda-karoq-1.0-tsi-1" is not canonical - slugify gives "skoda-karoq-10-tsi-1"
  x model "skoda-karoq-1.5-tsi-1" is not canonical - slugify gives "skoda-karoq-15-tsi-1"
  x model "skoda-karoq-2.0-tdi-4x4-1" is not canonical - slugify gives "skoda-karoq-20-tdi-4x4-1"
  x model "skoda-karoq-1.5-tsi-iv-1" is not canonical - slugify gives "skoda-karoq-15-tsi-iv-1"
  x model "skoda-karoq-sportline-2.0-tsi-4x4-1" is not canonical - slugify gives "skoda-karoq-sportline-20-tsi-4x4-1"
  x model "kia-uvo-10.25-inch-2023" is not canonical - slugify gives "kia-uvo-1025-inch-2023"
  x model "kia-uvo-12.3-inch-2024" is not canonical - slugify gives "kia-uvo-123-inch-2024"
  x model "burmester-5.1-system" is not canonical - slugify gives "burmester-51-system"
  x model "burmester-7.1-system" is not canonical - slugify gives "burmester-71-system"
  x model "burmester-high-end-5.1" is not canonical - slugify gives "burmester-high-end-51"
  x model "polish-&-wax" contains a character that breaks a URL path segment
  x model "polish-&-wax" is not canonical - slugify gives "polish-wax"
  x model "battery-60/20-ah" contains a character that breaks a URL path segment
  x model "battery-60/20-ah" is not canonical - slugify gives "battery-6020-ah"
  x model "fiat-paint-polish-&-wax" contains a character that breaks a URL path segment
  x model "fiat-paint-polish-&-wax" is not canonical - slugify gives "fiat-paint-polish-wax"
  x model "fiat-wheel-&-tire-cleaner" contains a character that breaks a URL path segment
  x model "fiat-wheel-&-tire-cleaner" is not canonical - slugify gives "fiat-wheel-tire-cleaner"
  x model "renault-megane-e-tech-100%-electric" contains a character that breaks a URL path segment
  x model "renault-megane-e-tech-100%-electric" is not canonical - slugify gives "renault-megane-e-tech-100-electric"
  x model "seal-1.5t" is not canonical - slugify gives "seal-15t"
  x model "qin-1.5t-dm-i" is not canonical - slugify gives "qin-15t-dm-i"
  x model "blade-battery-30.7-kwh" is not canonical - slugify gives "blade-battery-307-kwh"
  x model "blade-battery-44.9-kwh" is not canonical - slugify gives "blade-battery-449-kwh"
  x model "blade-battery-55.9-kwh" is not canonical - slugify gives "blade-battery-559-kwh"
  x model "blade-battery-86.4-kwh" is not canonical - slugify gives "blade-battery-864-kwh"
  x model "e-platform-3.0" is not canonical - slugify gives "e-platform-30"
  x model "b&w-diamond-surround-7-series" contains a character that breaks a URL path segment
  x model "b&w-diamond-surround-7-series" is not canonical - slugify gives "bw-diamond-surround-7-series"
  x model "b&w-diamond-surround-x7" contains a character that breaks a URL path segment
  x model "b&w-diamond-surround-x7" is not canonical - slugify gives "bw-diamond-surround-x7"
  x model "b&w-4d-diamond-surround" contains a character that breaks a URL path segment
  x model "b&w-4d-diamond-surround" is not canonical - slugify gives "bw-4d-diamond-surround"
  x model "b&w-reference-sound-system" contains a character that breaks a URL path segment
  x model "b&w-reference-sound-system" is not canonical - slugify gives "bw-reference-sound-system"
  x model "b&w-signature-diamond-elite" contains a character that breaks a URL path segment
  x model "b&w-signature-diamond-elite" is not canonical - slugify gives "bw-signature-diamond-elite"
  x model "hyundai-smart-audio-8.0" is not canonical - slugify gives "hyundai-smart-audio-80"
  . models_translations.slug not present yet - run 01-apply-schema.mjs

attribute option values
--------------------------------------------
  . collection not present yet - run 01-apply-schema.mjs

geo locations
--------------------------------------------
  . collection not present yet - run 01-apply-schema.mjs

Result
--------------------------------------------
  469 problem(s) found.

  Each one is a URL that will 404, resolve to the wrong entity, or
  shadow a modifier facet. Fix before the resolver ships.
```
