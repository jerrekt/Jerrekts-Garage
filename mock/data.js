// Mock data for the v1 preview. Visits and raw text come from BJ's OneNote log
// (Mnemosyne projects/e36-m3-service-log.md). Intervals and work types are
// placeholders until BJ confirms them (q74). Nothing here is invented history.
window.GARAGE = {
  today: "2026-11-05",
  car: { id: "e36-m3", name: "BMW E36 M3", body: "Sedan", engine: "S52", role: "Project car", status: "Engine work paused" },
  odometer: { miles: 193500, asOf: "2025-07", source: "Last service entry" },
  // system, type: preventive | corrective | diagnostic | upgrade | null (unclassified)
  visits: [
    { date: "2022-07-16", miles: 175200, raw: "Bought 175.2k", jobs: [["Bought", "Body", null]] },
    { date: "2022-07-21", miles: 175300, raw: "175.3k pennzoil Oil change 10w/40", jobs: [["Oil change 10W-40 Pennzoil", "Engine", "preventive"]] },
    { date: "2022-07", miles: 175300, raw: "175.3k Valve cover gasket Idle control hose replace Spark plugs", jobs: [["Valve cover gasket", "Engine", null], ["Idle control hose", "Engine", null], ["Spark plugs", "Engine", "preventive"]] },
    { date: "2022-08-14", miles: null, raw: "8/14/2022 trunk latch reinforcement", jobs: [["Trunk latch reinforcement", "Body", null]] },
    { date: "2022-08-18", miles: 175800, raw: "175.8k rotor and pad replacemnt / Rear left squeaking (Applied grease and anti seize to brake parts)", jobs: [["Rotors and pads", "Brakes", null], ["Rear left squeak: grease and anti-seize", "Brakes", "corrective"]] },
    { date: "2022-12-12", miles: 177500, raw: "177.5k Allignment and coilovers Engine Air filter", jobs: [["Alignment", "Suspension", null], ["Coilovers", "Suspension", "upgrade"], ["Engine air filter", "Engine", "preventive"]] },
    { date: "2023-01-03", miles: 177700, raw: "177.7k oil change 10w40 Mobil one", jobs: [["Oil change 10W-40 Mobil 1", "Engine", "preventive"]] },
    { date: "2023-01-31", miles: null, raw: "1/31/2023 swaybar end link", jobs: [["Sway bar end link", "Suspension", null]] },
    { date: "2023-02-01", miles: null, raw: "2/1/2023 asc throttle cable replacement", jobs: [["ASC throttle cable", "Engine", null]] },
    { date: "2023-04", miles: 178800, raw: "4-5/xx/23 Radiator Top and lower hose Electric fan Clutch fan delete Pulley kit 178.8k Oil change 5w40 Castro Diff oil change 75w140", jobs: [["Radiator", "Cooling", null], ["Upper and lower hoses", "Cooling", null], ["Electric fan", "Cooling", "upgrade"], ["Clutch fan delete", "Cooling", "upgrade"], ["Pulley kit", "Engine", null], ["Oil change 5W-40 Castrol", "Engine", "preventive"], ["Diff oil 75W-140", "Drivetrain", "preventive"]] },
    { date: "2024-01", miles: 182000, raw: "1/xx/24 182k 5w40 Castro 183k", jobs: [["Oil change 5W-40 Castrol", "Engine", "preventive"]] },
    { date: "2024-02-13", miles: 183000, raw: "2/13/24 183k Radiator Camshaft postion sensor M50 manifold Oil pan gasket Power steering pump rebuild Inner/outer tie rod Coolant Steering lines Camber arms bushings Oil change 5W40 castro Throttle cable Ball joints inner/outer Lolipop bushing", jobs: [["Radiator", "Cooling", null], ["Camshaft position sensor", "Engine", null], ["M50 manifold", "Engine", "upgrade"], ["Oil pan gasket", "Engine", null], ["Power steering pump rebuild", "Steering", null], ["Inner and outer tie rods", "Steering", null], ["Coolant", "Cooling", "preventive"], ["Steering lines", "Steering", null], ["Camber arm bushings", "Suspension", null], ["Oil change 5W-40 Castrol", "Engine", "preventive"], ["Throttle cable", "Engine", null], ["Inner and outer ball joints", "Suspension", null], ["Lollipop bushing", "Suspension", null]] },
    { date: "2024-03-07", miles: null, raw: "Allignment tech 3 3/7/24 (printout attached)", jobs: [["Alignment (Tech 3)", "Suspension", null]], attachment: true },
    { date: null, miles: 186000, raw: "186k oil change 5w40", jobs: [["Oil change 5W-40", "Engine", "preventive"]] },
    { date: null, miles: 189000, raw: "189k oil change 5w40 Radiator Rad fan", jobs: [["Oil change 5W-40", "Engine", "preventive"], ["Radiator", "Cooling", null], ["Radiator fan", "Cooling", null]] },
    { date: null, miles: 189700, raw: "189.7k tire change on rk003 Allignment", jobs: [["Tires on RK003", "Tires", "preventive"], ["Alignment", "Suspension", null]] },
    { date: "2025-07", miles: 193500, raw: "193.5k oil change 7/2025", jobs: [["Oil change 5W-40", "Engine", "preventive"]] }
  ],
  // PLACEHOLDER intervals (q74). match = words in a job name.
  plans: [
    { job: "Oil change", match: ["oil change"], miles: 5000, months: 12, safety: false },
    { job: "Coolant", match: ["coolant"], miles: null, months: 24, safety: false },
    { job: "Brake fluid", match: ["brake fluid"], miles: null, months: 24, safety: true },
    { job: "Engine air filter", match: ["air filter"], miles: 15000, months: 36, safety: false },
    { job: "Spark plugs", match: ["spark plugs"], miles: 30000, months: null, safety: false },
    { job: "Diff oil", match: ["diff oil"], miles: 30000, months: 48, safety: false },
    { job: "Alignment", match: ["alignment"], miles: 12000, months: null, safety: false },
    { job: "Brake pads", match: ["rotors and pads"], miles: 30000, months: null, safety: true }
  ],
  work: [
    { title: "S52 engine work", status: "Blocked", priority: "High", note: "Paused. Blockers not recorded yet.", cost: null }
  ],
  stories: [
    {
      id: "cooling",
      title: "Cooling system: three radiators in about 10k miles",
      component: "Radiator",
      events: [
        { miles: 178800, date: "2023-04", what: "Radiator, upper and lower hoses, electric fan, clutch fan delete, pulley kit" },
        { miles: 183000, date: "2024-02-13", what: "Radiator, coolant" },
        { miles: 189000, date: null, what: "Radiator, radiator fan" }
      ],
      steps: { Symptom: null, Diagnosis: null, "Confirmed cause": null, Action: "Radiator replaced three times (see events)", Verification: null, "Follow-up": null }
    }
  ]
};
