package com.backwoodsbrew.updates;

import androidx.core.content.FileProvider;

/** A distinct component keeps update APKs separate from Capacitor's file provider. */
public final class UpdateFileProvider extends FileProvider {}
