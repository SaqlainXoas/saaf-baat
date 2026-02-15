import nextJest from "next/jest.js";

const jest = nextJest({ dir: "./" });

/** @type {import('jest').Config} */
const config = jest({
  testEnvironment: "jsdom",
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  testPathIgnorePatterns: ["/node_modules/"],
});

export default config;
