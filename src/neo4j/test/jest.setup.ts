import { beforeAll } from '@jest/globals';

beforeAll(() => {
  // Set timeout for all tests
  jest.setTimeout(10000);
});