import 'package:flutter/material.dart';

/// ألوان موحّدة عبر التطبيق - نفس ألوان النسخة المكتبية ونسخة الويب
/// عشان الهوية البصرية تفضل واحدة في كل النسخ.
class AppColors {
  static const bg = Color(0xFFF3F4F8);
  static const cardBg = Color(0xFFFFFFFF);
  static const cardBorder = Color(0xFFE4E7EF);
  static const primary = Color(0xFF4F5DFF);
  static const primaryLight = Color(0xFFEEF0FF);
  static const success = Color(0xFF16A34A);
  static const successLight = Color(0xFFE9F9EF);
  static const danger = Color(0xFFE11D48);
  static const dangerLight = Color(0xFFFDEEF1);
  static const warning = Color(0xFFD97706);
  static const warningLight = Color(0xFFFEF6E7);
  static const textMain = Color(0xFF111827);
  static const textMuted = Color(0xFF6B7280);
  static const sidebarBg = Color(0xFF1E2233);
}

final Map<String, Color> tagBgColors = {
  "يحتاج متابعة خاصة": AppColors.dangerLight,
  "منتظم جدًا": AppColors.successLight,
  "جديد بالخدمة": AppColors.primaryLight,
};

final Map<String, Color> tagFgColors = {
  "يحتاج متابعة خاصة": AppColors.danger,
  "منتظم جدًا": AppColors.success,
  "جديد بالخدمة": AppColors.primary,
};

ThemeData buildAppTheme() {
  return ThemeData(
    useMaterial3: true,
    scaffoldBackgroundColor: AppColors.bg,
    fontFamily: "Tahoma",
    colorScheme: ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      primary: AppColors.primary,
      surface: AppColors.cardBg,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.cardBg,
      foregroundColor: AppColors.textMain,
      elevation: 0,
      centerTitle: false,
    ),
    cardTheme: CardTheme(
      color: AppColors.cardBg,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: const BorderSide(color: AppColors.cardBorder),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AppColors.cardBorder),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AppColors.cardBorder),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
      ),
    ),
  );
}
