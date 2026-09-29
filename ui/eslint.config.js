/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import eslint from '@eslint/js';
import tsParser from '@typescript-eslint/parser';
import tsEslintPlugin from '@typescript-eslint/eslint-plugin';
import reactPlugin from 'eslint-plugin-react';
import reactHooksPlugin from 'eslint-plugin-react-hooks';
import tsEslint from 'typescript-eslint';
import storybook from 'eslint-plugin-storybook';
import eslintConfigPrettier from 'eslint-config-prettier';

export default [
  {
    files: ['*.js', '*.jsx', '*.ts', '*.tsx']
  },
  {
    ignores: [
      'eslint.config.js',
      'node_modules/**',
      'dist/**',
      '.yarn/**',
      'src/config/**',
      'vite.config.js',
      'vite.config.d.ts',
      'vite.config.ts',
      '.tsbuildinfo',
      '!.storybook',
      'src/segment.ts'
    ]
  },
  eslint.configs.recommended,
  tsEslint.configs.eslintRecommended,
  {
    plugins: {
      'react-hooks': reactHooksPlugin
    },
    rules: reactHooksPlugin.configs.recommended.rules
  },
  ...storybook.configs['flat/recommended'],
  {
    name: 'phoenix-eslint',
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        project: './tsconfig.json'
      }
    },
    plugins: {
      '@typescript-eslint': tsEslintPlugin,
      react: reactPlugin
    },
    rules: {
      'block-spacing': ['warn', 'always'],
      'brace-style': ['warn', '1tbs'],
      curly: ['warn', 'all'],
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-inferrable-types': 'off',
      '@typescript-eslint/no-misused-promises': 'off',
      '@typescript-eslint/no-redundant-type-constituents': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-call': 'warn',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-return': 'off',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/restrict-template-expressions': 'off',
      '@typescript-eslint/unbound-method': 'off',
      'max-len': 'off',
      'no-async-promise-executor': 'warn',
      'no-mixed-spaces-and-tabs': 'error',
      'no-multi-spaces': 'warn',
      'no-trailing-spaces': 'warn',
      'no-unused-vars': 'off',
      'no-whitespace-before-property': 'error',
      'react/jsx-boolean-value': 'off',
      'react/jsx-indent-props': ['off'],
      'react/no-unknown-property': 'warn',
      'react/prop-types': 'off',
      'react/react-in-jsx-scope': 'off',
      'space-before-blocks': ['warn', 'always'],
      'space-before-function-paren': [
        'warn',
        {
          named: 'never',
          anonymous: 'ignore',
          asyncArrow: 'always'
        }
      ],
      'space-in-parens': ['warn', 'never']
    },
    settings: {
      react: {
        version: 'detect'
      }
    }
  },
  eslintConfigPrettier
];
