interface DbConfig {
  uri: string;
  username: string;
  password: string;
  database: string;
}

const localConfig: DbConfig = {
  uri: 'bolt://localhost:7687',
  username: 'neo4j',
  password: 'testpassword',
  database: 'neo4j'
};

const auraConfig: DbConfig = {
  uri: process.env.NEO4J_URI || '',
  username: process.env.NEO4J_USERNAME || '',
  password: process.env.NEO4J_PASSWORD || '',
  database: process.env.NEO4J_DATABASE || 'neo4j'
};

// Use TEST_ENV environment variable to switch between configurations
export const getTestConfig = (): DbConfig => {
  return process.env.TEST_ENV === 'aura' ? auraConfig : localConfig;
};
