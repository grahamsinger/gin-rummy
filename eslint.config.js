export default [
    {
        files: ["gin_rummy/web/static/**/*.js"],
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: "module",
            globals: {
                // Browser globals
                document: "readonly",
                window: "readonly",
                console: "readonly",
                fetch: "readonly",
                alert: "readonly",
                confirm: "readonly",
                setTimeout: "readonly",
                clearTimeout: "readonly",
                setInterval: "readonly",
                clearInterval: "readonly",
                HTMLElement: "readonly",
                MutationObserver: "readonly",
                localStorage: "readonly",
                requestAnimationFrame: "readonly",
                URLSearchParams: "readonly",
            },
        },
        rules: {
            "no-unused-vars": ["warn", { vars: "all", args: "none", varsIgnorePattern: "^_" }],
            "no-undef": "error",
            "no-unreachable": "error",
            "no-self-assign": "error",
            "no-constant-condition": "warn",
            "no-empty": "warn",
        },
    },
];
