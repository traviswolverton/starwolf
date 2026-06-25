# Southeast Sites Staging — MS, AL, GA, FL, LA

Candidate stargazing sites to evaluate via the Bortle API before seeding.
Run `python scripts/bortle_score_candidates.py` to populate the Bortle column.

## Schema note

The current `site_type` CHECK constraint only allows `tx_state_park` for state parks.
Before seeding these, either:
- Add `'state_park'` to the constraint and migrate existing `tx_state_park` rows, OR
- Add state-specific values (`ms_state_park`, `al_state_park`, etc.)

Recommended: generalize to `state_park` — the state is already inferable from coordinates.

---

## Candidate Sites

| Name | State | Lat | Lon | Proposed site_type | Notes |
|------|-------|-----|-----|--------------------|-------|
| Tishomingo State Park | MS | 34.6067 | -88.1803 | state_park | NE Mississippi; rocky terrain, relatively isolated |
| De Soto National Forest (Tuxachanie Trail) | MS | 30.6000 | -89.0500 | national_forest | Southern MS; limited nearby development |
| Homochitto National Forest (Pipes Lake) | MS | 31.4014 | -91.0364 | national_forest | SW Mississippi; Pipes Lake rec area |
| Wall Doxey State Park | MS | 34.7528 | -89.3483 | state_park | N Mississippi; spring-fed lake; rural setting |
| Cheaha State Park | AL | 33.4858 | -85.8050 | state_park | Highest point in Alabama (2,413 ft); elevated horizon |
| Conecuh National Forest | AL | 31.2490 | -86.7947 | national_forest | S Alabama; longleaf pine; low population density |
| Bankhead National Forest / Sipsey Wilderness | AL | 34.3000 | -87.3500 | national_forest | NW Alabama; largest wilderness east of the Mississippi |
| DeSoto State Park | AL | 34.4893 | -85.6151 | state_park | NE Alabama; atop Lookout Mountain plateau |
| Little River Canyon National Preserve | AL | 34.3706 | -85.6151 | national_park | NE Alabama; canyon rim; dark ridge line to the south |
| Cloudland Canyon State Park | GA | 34.8332 | -85.4832 | state_park | NW Georgia; canyon setting reduces horizon light dome |
| Vogel State Park | GA | 34.7640 | -83.9286 | state_park | N Georgia mountains; bowl topography shields some light |
| Black Rock Mountain State Park | GA | 34.9073 | -83.4018 | state_park | Highest state park in GA (3,640 ft); mountain ridgeline |
| Unicoi State Park | GA | 34.7294 | -83.7165 | state_park | NE Georgia mountains near Helen |
| Amicalola Falls State Park | GA | 34.5619 | -84.2485 | state_park | NW Georgia; approach to Appalachian Trail |
| Okefenokee NWR (Stephen Foster SP) | GA | 30.7283 | -82.4274 | national_park | SE Georgia; very flat, but extremely low population density |
| Kissimmee Prairie Preserve State Park | FL | 27.5997 | -81.0506 | ida_certified | IDA Dark Sky Park; flattest, darkest open prairie in FL |
| Jonathan Dickinson State Park | FL | 27.0076 | -80.1078 | state_park | SE Florida; river swamp; limited but accessible |
| Highlands Hammock State Park | FL | 27.4858 | -81.5353 | state_park | C Florida; old-growth hammock; some isolation from I-4 corridor |
| Lake Kissimmee State Park | FL | 27.9581 | -81.3862 | state_park | C Florida; open prairie/marsh; away from urban cores |
| Ocala National Forest (Lake Oklawaha) | FL | 29.2000 | -81.8000 | national_forest | C Florida; large contiguous forest block |
| Apalachicola National Forest (Camel Lake) | FL | 30.1000 | -84.8000 | national_forest | NW Florida panhandle; remote camping area |
| Fakahatchee Strand Preserve State Park | FL | 25.9736 | -81.3681 | state_park | SW Florida; remote swamp; very low development nearby |
| Everglades National Park (Flamingo) | FL | 25.1378 | -80.9256 | national_park | Southernmost point; remote; minimal light to the south |
| Big Cypress National Preserve | FL | 26.0000 | -81.0000 | national_park | SW Florida; vast wilderness; dark but humid |
| Kisatchie National Forest (Wild Azalea area) | LA | 31.3000 | -92.5000 | national_forest | C Louisiana; largest national forest in the state |
| Chicot State Park | LA | 30.7833 | -92.2833 | state_park | SC Louisiana; around Lake Chicot; rural |
| Hodges Gardens State Park | LA | 31.2350 | -93.2750 | state_park | W Louisiana; 4,700-acre garden/wilderness; remote |
| Lake Bistineau State Park | LA | 32.5333 | -93.3667 | state_park | NW Louisiana; cypress-tupelo swamp; low population |
| Poverty Point Reservoir State Park | LA | 32.6340 | -91.4030 | state_park | NE Louisiana; flatlands; isolated from major cities |
