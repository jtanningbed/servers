
export const schemas = {
  Person: {
    properties: {
      name: { type: 'string' },
      age: { type: 'number' },
      email: { type: 'string' },
    },
  },
  Company: {
    properties: {
      name: { type: 'string' },
      industry: { type: 'string' },
      employees: { type: 'array', items: { $ref: '#/definitions/Person' } },
    },
    definitions: {
      Person: {
        $ref: '#/Person',
      },
    },
  },
};
