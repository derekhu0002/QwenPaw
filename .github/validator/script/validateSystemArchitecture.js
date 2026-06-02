const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..', '..', '..');
const graphPath = path.join(repoRoot, 'design', 'KG', 'SystemArchitecture.json');
const schemaPathCandidates = [
    path.join(repoRoot, '.github', 'argoschema', 'SystemArchitecture.schema.json'),
    path.join(repoRoot, 'schema', 'SystemArchitecture.schema.json'),
];

function main() {
    const schemaPath = schemaPathCandidates.find(candidate => fs.existsSync(candidate));
    if (!schemaPath) {
        fail(`Schema file is missing. Checked: ${schemaPathCandidates.map(candidate => path.relative(repoRoot, candidate)).join(', ')}`);
    }

    if (!fs.existsSync(graphPath)) {
        fail('System architecture file is missing at design/KG/SystemArchitecture.json');
    }

    const schema = parseJson(schemaPath, path.relative(repoRoot, schemaPath));
    const document = parseJson(graphPath, 'design/KG/SystemArchitecture.json');
    const errors = [];
    validateAgainstSchema(document, schema, '#', errors, schema);

    if (errors.length > 0) {
        console.error('SystemArchitecture validation failed:');
        for (const error of errors) {
            console.error(`- ${error}`);
        }
        process.exit(1);
    }

    console.log('SystemArchitecture validation passed for: design/KG/SystemArchitecture.json');
}

function parseJson(filePath, label) {
    try {
        return JSON.parse(fs.readFileSync(filePath, 'utf8'));
    } catch (error) {
        fail(`Failed to parse ${label}: ${String(error)}`);
    }
}

function validateAgainstSchema(value, schemaNode, pointer, errors, rootSchema) {
    if (!schemaNode || typeof schemaNode !== 'object') {
        return;
    }

    const resolvedSchema = schemaNode.$ref ? resolveRef(schemaNode.$ref, rootSchema, errors, pointer) : schemaNode;
    if (!resolvedSchema) {
        return;
    }

    if (resolvedSchema.const !== undefined && !isDeepStrictEqual(value, resolvedSchema.const)) {
        errors.push(`${pointer} must equal ${JSON.stringify(resolvedSchema.const)}`);
        return;
    }

    if (resolvedSchema.enum && !resolvedSchema.enum.some(option => isDeepStrictEqual(option, value))) {
        errors.push(`${pointer} must be one of: ${resolvedSchema.enum.map(option => JSON.stringify(option)).join(', ')}`);
    }

    if (resolvedSchema.type) {
        validateType(value, resolvedSchema.type, pointer, errors);
        if (!typeMatches(value, resolvedSchema.type)) {
            return;
        }
    }

    if (typeof resolvedSchema.minItems === 'number') {
        if (!Array.isArray(value) || value.length < resolvedSchema.minItems) {
            errors.push(`${pointer} must contain at least ${resolvedSchema.minItems} item(s)`);
        }
    }

    if (resolvedSchema.type === 'object') {
        validateObject(value, resolvedSchema, pointer, errors, rootSchema);
        return;
    }

    if (resolvedSchema.type === 'array') {
        validateArray(value, resolvedSchema, pointer, errors, rootSchema);
    }
}

function validateObject(value, schemaNode, pointer, errors, rootSchema) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return;
    }

    const properties = schemaNode.properties || {};
    const required = Array.isArray(schemaNode.required) ? schemaNode.required : [];

    for (const key of required) {
        if (!(key in value)) {
            errors.push(`${pointer} is missing required property '${key}'`);
        }
    }

    if (schemaNode.additionalProperties === false) {
        for (const key of Object.keys(value)) {
            if (!(key in properties)) {
                errors.push(`${pointer} contains unsupported property '${key}'`);
            }
        }
    }

    for (const [key, propertySchema] of Object.entries(properties)) {
        if (key in value) {
            validateAgainstSchema(value[key], propertySchema, `${pointer}.${key}`, errors, rootSchema);
        }
    }
}

function validateArray(value, schemaNode, pointer, errors, rootSchema) {
    if (!Array.isArray(value)) {
        return;
    }

    if (schemaNode.items) {
        value.forEach((entry, index) => {
            validateAgainstSchema(entry, schemaNode.items, `${pointer}[${index}]`, errors, rootSchema);
        });
    }
}

function validateType(value, expectedType, pointer, errors) {
    if (!typeMatches(value, expectedType)) {
        errors.push(`${pointer} must be of type ${expectedType}`);
    }
}

function typeMatches(value, expectedType) {
    switch (expectedType) {
        case 'object':
            return value !== null && typeof value === 'object' && !Array.isArray(value);
        case 'array':
            return Array.isArray(value);
        case 'string':
            return typeof value === 'string';
        case 'number':
            return typeof value === 'number' && Number.isFinite(value);
        case 'boolean':
            return typeof value === 'boolean';
        default:
            return true;
    }
}

function resolveRef(ref, rootSchema, errors, pointer) {
    if (!ref.startsWith('#/')) {
        errors.push(`${pointer} uses unsupported $ref '${ref}'`);
        return undefined;
    }

    const segments = ref.slice(2).split('/');
    let current = rootSchema;
    for (const segment of segments) {
        if (!current || typeof current !== 'object' || !(segment in current)) {
            errors.push(`${pointer} references missing schema path '${ref}'`);
            return undefined;
        }
        current = current[segment];
    }

    return current;
}

function isDeepStrictEqual(left, right) {
    return JSON.stringify(left) === JSON.stringify(right);
}

function fail(message) {
    console.error(`SystemArchitecture validation failed: ${message}`);
    process.exit(1);
}

main();