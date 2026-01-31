export default [
    {
        files: ["gin_rummy/web/static/**/*.js"],
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: "script",
            globals: {
                // Browser globals
                document: "readonly",
                window: "readonly",
                console: "readonly",
                fetch: "readonly",
                alert: "readonly",
                confirm: "readonly",
                setTimeout: "readonly",
                setInterval: "readonly",
                clearInterval: "readonly",
                HTMLElement: "readonly",
                MutationObserver: "readonly",
                Chart: "readonly",
            },
        },
        rules: {
            "no-unused-vars": ["warn", { vars: "all", args: "none", varsIgnorePattern: "^_" }],
            "no-unreachable": "error",
            "no-self-assign": "error",
            "no-constant-condition": "warn",
            "no-empty": "warn",
        },
    },
];
