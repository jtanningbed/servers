// ... rest of your index.ts file remains the same ...

// Change the condition at the bottom to:
if (process.argv[1] === new URL(import.meta.url).pathname) {
  main().catch((error) => {
    console.error('Fatal error:', error);
    process.exit(1);
  });
}
