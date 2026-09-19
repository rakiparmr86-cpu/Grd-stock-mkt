import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { useAuth } from '@/context/auth';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export function LoginScreen() {
  const { signIn, error } = useAuth();
  const theme = useTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = async () => {
    if (!email.trim() || !password || busy) return;
    setBusy(true);
    setLocalError(null);
    try {
      await signIn(email.trim(), password);
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ThemedView style={styles.root}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.select({ ios: 'padding', android: 'height' })}>
        <ScrollView
          style={styles.flex}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled">
          <SafeAreaView style={styles.safeArea}>
            <ThemedView style={styles.card} type="backgroundElement">
              <ThemedText type="title" style={styles.title}>
                grd-stk-mkt
              </ThemedText>
              <ThemedText themeColor="textSecondary" style={styles.subtitle}>
                Sign in to run an analysis
              </ThemedText>

              <ThemedText type="smallBold" style={styles.label}>
                Email or username
              </ThemedText>
              <TextInput
                style={[styles.input, { color: theme.text, borderColor: theme.backgroundSelected }]}
                value={email}
                onChangeText={setEmail}
                placeholder="you@example.com"
                placeholderTextColor={theme.textSecondary}
                autoCapitalize="none"
                autoCorrect={false}
                textContentType="username"
                returnKeyType="next"
              />

              <ThemedText type="smallBold" style={styles.label}>
                Password
              </ThemedText>
              <ThemedView style={styles.passwordWrap}>
                <TextInput
                  style={[
                    styles.input,
                    styles.passwordInput,
                    { color: theme.text, borderColor: theme.backgroundSelected },
                  ]}
                  value={password}
                  onChangeText={setPassword}
                  placeholder="••••••••"
                  placeholderTextColor={theme.textSecondary}
                  secureTextEntry={!showPassword}
                  autoCapitalize="none"
                  autoCorrect={false}
                  textContentType="password"
                  returnKeyType="go"
                  onSubmitEditing={submit}
                />
                <Pressable
                  onPress={() => setShowPassword((v) => !v)}
                  hitSlop={8}
                  accessibilityRole="button"
                  accessibilityLabel={showPassword ? 'Hide password' : 'Show password'}
                  style={styles.toggle}>
                  <ThemedText type="link">{showPassword ? 'Hide' : 'Show'}</ThemedText>
                </Pressable>
              </ThemedView>

              {(localError || error) && (
                <ThemedText themeColor="text" style={styles.error}>
                  {localError || error}
                </ThemedText>
              )}

              <Pressable
                onPress={submit}
                disabled={busy || !email.trim() || !password}
                style={({ pressed }) => [
                  styles.button,
                  { opacity: busy || !email.trim() || !password ? 0.5 : pressed ? 0.8 : 1 },
                ]}>
                {busy ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <ThemedText style={styles.buttonText}>Sign in</ThemedText>
                )}
              </Pressable>
            </ThemedView>
          </SafeAreaView>
        </ScrollView>
      </KeyboardAvoidingView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  safeArea: {
    width: '100%',
    alignItems: 'center',
    paddingHorizontal: Spacing.four,
  },
  card: {
    width: '100%',
    maxWidth: 380,
    borderRadius: Spacing.four,
    padding: Spacing.five,
  },
  title: {
    fontSize: 28,
    lineHeight: 34,
  },
  subtitle: {
    marginTop: Spacing.one,
    marginBottom: Spacing.four,
  },
  label: {
    marginBottom: Spacing.one,
  },
  input: {
    borderWidth: 1,
    borderRadius: Spacing.two,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    marginBottom: Spacing.three,
    fontSize: 16,
  },
  passwordWrap: {
    justifyContent: 'center',
    backgroundColor: 'transparent',
  },
  passwordInput: {
    paddingRight: 64,
  },
  toggle: {
    position: 'absolute',
    right: Spacing.three,
    top: 0,
    bottom: Spacing.three,
    justifyContent: 'center',
  },
  error: {
    color: '#d92d20',
    marginBottom: Spacing.three,
  },
  button: {
    backgroundColor: '#208AEF',
    borderRadius: Spacing.two,
    paddingVertical: Spacing.three,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: {
    color: '#fff',
    fontWeight: '600',
  },
});
