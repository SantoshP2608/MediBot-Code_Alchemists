export const sampleSandbox = {
  isDemo: true,
  name: "Example Medicine 500",
  category: "Sample tablet · 10-tablet pack",
  composition: "Example ingredient 500 mg",
  baseMrp: 100,
  maxSavings: 30,
  alternatives: [
    {
      id: "sample-a",
      name: "Example Alternative A",
      manufacturer: "Sample manufacturer A",
      matchLabel: "Sample exact match",
      mrp: 70,
      savings: 30,
      quotes: [
        {
          pharmacy: "Sample pharmacy A",
          price: 65,
          delivery: "Example: tomorrow",
        },
        {
          pharmacy: "Sample pharmacy B",
          price: 68,
          delivery: "Example: 24–48 hours",
        },
      ],
    },
    {
      id: "sample-b",
      name: "Example Alternative B",
      manufacturer: "Sample manufacturer B",
      matchLabel: "Sample exact match",
      mrp: 80,
      savings: 20,
      quotes: [
        {
          pharmacy: "Sample pharmacy C",
          price: 75,
          delivery: "Example: store pickup",
        },
      ],
    },
  ],
};