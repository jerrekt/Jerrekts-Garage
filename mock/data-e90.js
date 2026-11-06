// E90 328i visits from BJ's OneNote (Mnemosyne projects/e90-328i-service-log.md). No VIN here: this repo is public.
// Intervals are placeholders (same as the E36) until BJ sets his own.
window.GARAGE_E90 = {
  car: { id: "e90", name: "BMW E90 328i", engine: "N51" },
  odometer: { miles: 163500, asOf: null, source: "Last service entry" },
  visits: [
    { date: null, miles: 140800, raw: "140.8k oil change 5w30 Rotate", jobs: [["Oil change 5W-30", "Engine", "preventive"], ["Tire rotation", "Tires", "preventive"]] },
    { date: null, miles: 142321, raw: "Stevens Creek BMW multi-point inspection, all items passing, tread 6/32+", jobs: [["Dealer multi-point inspection", "Body", "diagnostic"]], attachment: true },
    { date: "2024-03", miles: 145000, raw: "3/2024 145k oil change5w40 Rotate", jobs: [["Oil change 5W-40", "Engine", "preventive"], ["Tire rotation", "Tires", "preventive"]] },
    { date: null, miles: 149300, raw: "149.3k tires needed", jobs: [["Noted: tires needed", "Tires", "diagnostic"]] },
    { date: null, miles: 150000, raw: "150k apex/tires", jobs: [["Apex wheels and tires", "Tires", null]] },
    { date: null, miles: 152000, raw: "152k oil 5w40", jobs: [["Oil change 5W-40", "Engine", "preventive"]] },
    { date: null, miles: 153000, raw: "153k Fender liners fixed", jobs: [["Fender liners fixed", "Body", "corrective"]] },
    { date: "2025-11-26", miles: 157500, raw: "157.5k 5w30 Mobil 1 extend 11/26/2025", jobs: [["Oil change 5W-30 Mobil 1", "Engine", "preventive"]] },
    { date: null, miles: 162000, raw: "162k valve cover and gasket replaced Underside cleaning Spark plugs", jobs: [["Valve cover and gasket", "Engine", null], ["Underside cleaning", "Body", null], ["Spark plugs", "Engine", "preventive"]] },
    { date: null, miles: 163500, raw: "163.5k oil change 5w 40 euro mobil", jobs: [["Oil change 5W-40 Mobil", "Engine", "preventive"]] }
  ]
};
