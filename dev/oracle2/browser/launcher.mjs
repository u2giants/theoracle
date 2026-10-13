// Includes module-load denials in the same secret-free startup failure boundary.
try{await import('/app/apps/web/.next/native-browser-bootstrap/native-browser-boot.js');}
catch{console.error('Native invented browser startup denied.');process.exit(1);}
